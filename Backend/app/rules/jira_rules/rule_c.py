"""
Rule set C: Solution knowledge base.

Answers the practice lead question: has anyone here solved this before?

Rules
-----
C-01  Keep only tickets with a real resolution
C-02  Strip signatures, bot comments, and quoted replies
C-03  Redact sensitive content before storage
C-04  Separate the problem text from the solution text
C-05  Chunk long text into overlapping, sentence-aware passages
C-06  Tag each entry by function area and M3 version
C-07  Down-rank answers written for a different M3 version
C-08  Link near duplicates (placeholder, filled by the Vector DB writer)
C-09  Suggest prior resolutions on arrival (placeholder, filled by writer)

Ordering note
-------------
C-02 must run before C-03 so redaction operates on cleaned text, and C-03
must run before C-04 so problem and solution are extracted from text that
is already safe to store. C-03 is not optional: removing content from an
index is far harder than never adding it.
"""

import re


# Regex patterns for content that must never reach the knowledge base.
# Each entry is (pattern, label). Only the label is recorded; the matched
# value is discarded to ensure information confidentiality.
SENSITIVE_PATTERNS = [
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email"),
    (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "phone"),
    (r"(?i)(api[_\- ]?key|secret|password|token)\s*[:=]\s*\S+", "credential"),
    (r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b", "card_number"),
]

# Patterns for lines that carry no meaning in a solution. These are
# removed from each comment before it enters the knowledge base.
NOISE_PATTERNS = [
    r"^\s*--\s*$",
    r"^\s*Sent from my .*$",
    r"^\s*On .* wrote:\s*$",
    r"^\s*\[bot\]",
    r"^\s*This is an automated message.*$",
]

# Minimum length for the final comment to be considered a real solution.
C01_MIN_SOLUTION_LENGTH = 40

# Minimum length for a comment to be considered substantial during
# problem/solution separation in C-04.
C04_MIN_SUBSTANTIAL = 40


def _comment_text(comment):
    """
    Return the best available text for a comment.

    Prefers the cleaned body produced by C-02, falls back to the original
    body, and finally to an empty string. This lets C-04 run safely even
    if C-02 has not been applied yet (for example in unit tests).
    """
    return comment.get("body_clean") or comment.get("body") or ""


# ---------------------------------------------------------------------------
# C-01 Take only real resolutions
# ---------------------------------------------------------------------------
# A resolution must exist AND the last substantial comment must be
# longer than a trivial "fixed". This is a gate, not a filter: a ticket
# that fails C-01 is excluded from the knowledge base but is not
# removed from the pipeline.
# ---------------------------------------------------------------------------

def rule_c_01_real_resolutions_only(ticket):
    """
    Flag tickets that are real knowledge-base candidates.

    A ticket qualifies if it has a resolution AND its last comment is at
    least C01_MIN_SOLUTION_LENGTH characters long.

    Writes to rule_results:
        c01_is_real_resolution    (bool)
        c01_last_comment_length   (int)
    """
    resolution = ticket.get("resolution")
    comments = ticket.get("comments", [])

    last_comment_text = _comment_text(comments[-1]) if comments else ""

    has_resolution = bool(resolution)
    has_substance = len(last_comment_text.strip()) >= C01_MIN_SOLUTION_LENGTH

    ticket["rule_results"]["c01_is_real_resolution"] = has_resolution and has_substance
    ticket["rule_results"]["c01_last_comment_length"] = len(last_comment_text.strip())
    return ticket


# ---------------------------------------------------------------------------
# C-02 Strip the noise
# ---------------------------------------------------------------------------
# Writes a body_clean on each comment. The original body is preserved so
# the record remains auditable.
# ---------------------------------------------------------------------------

def rule_c_02_strip_noise(ticket):
    """
    Remove noise lines from every comment body.

    Writes body_clean on each comment. The original body is left
    untouched so the raw record can still be inspected.
    """
    for comment in ticket.get("comments", []):
        body = comment.get("body") or ""

        kept_lines = [
            line for line in body.splitlines()
            if not any(re.match(pattern, line.strip()) for pattern in NOISE_PATTERNS)
        ]

        comment["body_clean"] = "\n".join(kept_lines).strip()
    return ticket


# ---------------------------------------------------------------------------
# C-03 Remove anything sensitive
# ---------------------------------------------------------------------------
# Destructive on purpose: redaction happens before storage. Records only
# the pattern type found, never the value.
# ---------------------------------------------------------------------------

def rule_c_03_redact_sensitive(ticket):
    """
    Redact sensitive content from the description and every comment.

    Replaces matches with a label like [EMAIL_REDACTED]. Records the
    type and count of findings, never the matched value.

    Writes:
        ticket["description"]              (redacted in place)
        comment["body_clean"]              (redacted in place)

    Writes to rule_results:
        c03_sensitive_found    (bool)
        c03_sensitive_types    (list[str])
        c03_sensitive_count    (int)
    """
    findings = []

    def redact(text):
        if not text:
            return text
        for pattern, label in SENSITIVE_PATTERNS:
            for _ in re.finditer(pattern, text):
                findings.append(label)
            text = re.sub(pattern, f"[{label.upper()}_REDACTED]", text)
        return text

    ticket["description"] = redact(ticket.get("description") or "")

    for comment in ticket.get("comments", []):
        comment["body_clean"] = redact(comment.get("body_clean") or "")

    ticket["rule_results"]["c03_sensitive_found"] = len(findings) > 0
    ticket["rule_results"]["c03_sensitive_types"] = sorted(set(findings))
    ticket["rule_results"]["c03_sensitive_count"] = len(findings)
    return ticket


# ---------------------------------------------------------------------------
# C-04 Separate problem from solution
# ---------------------------------------------------------------------------
# Problem text comes from the description and the first two comments.
# Solution text comes from the last substantial comment.
# ---------------------------------------------------------------------------

def rule_c_04_separate_problem_and_solution(ticket):
    """
    Split the ticket text into a problem statement and a solution.

    Problem  = description + first two comments
    Solution = last comment of at least C04_MIN_SUBSTANTIAL characters

    Writes to rule_results:
        c04_problem    (str)
        c04_solution   (str)
    """
    problem_parts = []

    if ticket.get("description"):
        problem_parts.append(ticket["description"].strip())

    for comment in ticket.get("comments", [])[:2]:
        text = _comment_text(comment).strip()
        if text:
            problem_parts.append(text)

    solution = ""
    for comment in reversed(ticket.get("comments", [])):
        text = _comment_text(comment).strip()
        if len(text) >= C04_MIN_SUBSTANTIAL:
            solution = text
            break

    ticket["rule_results"]["c04_problem"] = "\n\n".join(problem_parts).strip()
    ticket["rule_results"]["c04_solution"] = solution
    return ticket


# ---------------------------------------------------------------------------
# C-05 Chunk long text sensibly
# ---------------------------------------------------------------------------
# Overlapping windows, never cut mid-sentence. Guards against the
# infinite loop case where overlap >= chunk_size by shrinking overlap.
# ---------------------------------------------------------------------------

def rule_c_05_chunk_long_text(ticket, chunk_size=800, overlap=100):
    """
    Split the problem + solution text into overlapping passages.

    Each chunk tries to end at a sentence boundary (". ") rather than
    mid-sentence. Consecutive chunks overlap by `overlap` characters so
    a search that straddles the boundary still finds a usable answer.

    Writes to rule_results:
        c05_chunks  (list[str])
    """
    text = (
        (ticket["rule_results"].get("c04_problem") or "")
        + "\n\n"
        + (ticket["rule_results"].get("c04_solution") or "")
    ).strip()

    if not text:
        ticket["rule_results"]["c05_chunks"] = []
        return ticket

    # Prevent an infinite loop when overlap is larger than chunk_size.
    if overlap >= chunk_size:
        overlap = chunk_size // 4

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        # Prefer to end at a sentence boundary, but only if the boundary
        # is far enough into the chunk to be worth using.
        if end < len(text):
            boundary = text.rfind(". ", start, end)
            if boundary != -1 and boundary > start + chunk_size // 2:
                end = boundary + 1

        chunks.append(text[start:end].strip())

        if end >= len(text):
            break

        # Ensure the next start is strictly greater than the last one,
        # even if overlap were misconfigured.
        start = max(end - overlap, start + 1)

    ticket["rule_results"]["c05_chunks"] = [chunk for chunk in chunks if chunk]
    return ticket


# ---------------------------------------------------------------------------
# C-06 Tag by function and version
# ---------------------------------------------------------------------------

def rule_c_06_tag_function_and_version(ticket):
    """
    Tag the entry with the function area and M3 version it applies to.

    Writes to rule_results:
        c06_function_area   (str | None)
        c06_m3_version      (str | None)
    """
    ticket["rule_results"]["c06_function_area"] = ticket.get("function_area")
    ticket["rule_results"]["c06_m3_version"] = ticket.get("m3_program_code")
    return ticket


# ---------------------------------------------------------------------------
# C-07 Down rank stale answers
# ---------------------------------------------------------------------------
# Compares the asking ticket's M3 version against the answer's version.
# In ERP support an old answer is often actively wrong.
# ---------------------------------------------------------------------------

def rule_c_07_down_rank_stale(ticket):
    """
    Flag the entry as stale when its M3 version differs from the ticket's.

    Writes to rule_results:
        c07_is_stale  (bool)
    """
    asking_version = ticket.get("m3_program_code")
    answer_version = ticket["rule_results"].get("c06_m3_version")

    ticket["rule_results"]["c07_is_stale"] = bool(
        asking_version and answer_version and asking_version != answer_version
    )
    return ticket


# ---------------------------------------------------------------------------
# C-08 Link near duplicates
# ---------------------------------------------------------------------------
# Placeholder. The Vector DB writer fills this after the rules run.
# ---------------------------------------------------------------------------

def rule_c_08_link_near_duplicates(ticket):
    """
    Reserve a field for the near-duplicate link.

    The actual lookup requires the Vector DB, which is not available to
    the rule engine. The writer step fills this field after the rules run.

    Writes to rule_results:
        c08_duplicate_of  (str | None)
    """
    ticket["rule_results"].setdefault("c08_duplicate_of", None)
    return ticket


# ---------------------------------------------------------------------------
# C-09 Suggest on arrival
# ---------------------------------------------------------------------------
# Placeholder. The Vector DB writer fills this after the rules run.
# ---------------------------------------------------------------------------

def rule_c_09_suggest_on_arrival(ticket):
    """
    Reserve a field for suggested prior resolutions.

    The actual lookup requires the Vector DB. The writer step fills this
    field after the rules run.

    Writes to rule_results:
        c09_suggested_resolutions  (list[dict])
    """
    ticket["rule_results"].setdefault("c09_suggested_resolutions", [])
    return ticket


RULES = [
    rule_c_01_real_resolutions_only,
    rule_c_02_strip_noise,
    rule_c_03_redact_sensitive,
    rule_c_04_separate_problem_and_solution,
    rule_c_05_chunk_long_text,
    rule_c_06_tag_function_and_version,
    rule_c_07_down_rank_stale,
    rule_c_08_link_near_duplicates,
    rule_c_09_suggest_on_arrival,
]