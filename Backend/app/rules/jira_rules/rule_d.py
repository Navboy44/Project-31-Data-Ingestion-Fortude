"""
Rule set D: Client health early warning.

Answers the client services director question: which client is about to
escalate, and can we get there first?

Rules
-----
D-01  Report how many status changes the ticket had
D-02  Split elapsed time into waiting time and working time
D-03  Count reopens
D-04  Build a stable error signature for cross-ticket recurrence
D-05  Flag tickets raised by senior client staff
D-06  Record the client baseline injected before the rules run
D-07  Produce this ticket's contribution to the client health score

Cross-ticket aggregation
------------------------
D-04 grouping, D-06 baseline comparison, and D-07 client scoring are
completed by aggregators in jira_rule_engine.py, because they need to
look at many tickets at once.
"""


# Statuses that represent the client or the desk waiting, not working.
WAITING_STATUSES = {
    "Waiting for Customer",
    "Waiting for Support",
    "Blocked",
    "On Hold",
}

# Statuses that represent active work.
WORKING_STATUSES = {
    "In Progress",
    "In Review",
    "In Development",
    "In Testing",
}

# Job-title keywords that indicate the raiser is senior. Used by D-05
# because Jira only exposes accountType, not job title.
SENIOR_ROLES = {"manager", "admin", "executive", "director", "senior"}


# ---------------------------------------------------------------------------
# D-01 Build the history
# ---------------------------------------------------------------------------
# The mapper already built status_history. This rule only reports the
# count so a downstream writer can spot tickets with no movement.
# ---------------------------------------------------------------------------

def rule_d_01_build_history(ticket):
    """
    Report the size of the status history.

    Writes to rule_results:
        d01_change_count    (int)
        d01_has_movement    (bool)
    """
    status_history = ticket.get("status_history", [])
    ticket["rule_results"]["d01_change_count"] = len(status_history)
    ticket["rule_results"]["d01_has_movement"] = len(status_history) > 0
    return ticket


# ---------------------------------------------------------------------------
# D-02 Separate waiting from working
# ---------------------------------------------------------------------------
# Iterates the status_history durations and buckets them into waiting vs
# working. Duration is attributed to the previous status, because it
# represents time spent in that state before the transition happened.
# ---------------------------------------------------------------------------

def rule_d_02_separate_waiting_from_working(ticket):
    """
    Split elapsed time into waiting time and working time.

    Iterates each status change and attributes the duration to the
    *previous* status. Waiting statuses accumulate into waiting time,
    working statuses into working time.

    Writes to rule_results:
        d02_waiting_seconds    (int)
        d02_working_seconds    (int)
        d02_waiting_share      (float)
    """
    waiting_seconds = 0
    working_seconds = 0

    for status_change in ticket.get("status_history", []):
        duration = status_change.get("duration_in_previous_status_seconds") or 0
        previous_status = status_change.get("from")

        if previous_status in WAITING_STATUSES:
            waiting_seconds += duration
        elif previous_status in WORKING_STATUSES:
            working_seconds += duration

    total_seconds = waiting_seconds + working_seconds

    ticket["rule_results"]["d02_waiting_seconds"] = waiting_seconds
    ticket["rule_results"]["d02_working_seconds"] = working_seconds
    ticket["rule_results"]["d02_waiting_share"] = (
        round(waiting_seconds / total_seconds, 2) if total_seconds else 0
    )
    return ticket


# ---------------------------------------------------------------------------
# D-03 Count reopens
# ---------------------------------------------------------------------------
# The mapper already flagged each reopen in status_history.is_reopen.
# ---------------------------------------------------------------------------

def rule_d_03_count_reopens(ticket):
    """
    Count how many times the ticket was reopened.

    A reopen is a transition from a terminal status (Resolved, Closed,
    Done) back to a non-terminal one. The mapper sets is_reopen on each
    status change, so this rule only aggregates.

    Writes to rule_results:
        d03_reopen_count   (int)
        d03_has_reopen     (bool)
    """
    reopen_count = sum(
        1 for status_change in ticket.get("status_history", [])
        if status_change.get("is_reopen")
    )

    ticket["rule_results"]["d03_reopen_count"] = reopen_count
    ticket["rule_results"]["d03_has_reopen"] = reopen_count > 0
    return ticket


# ---------------------------------------------------------------------------
# D-04 Detect recurrence
# ---------------------------------------------------------------------------
# Per ticket it builds a stable error signature. The aggregator groups by
# client + function + signature over 90 days to find patterns.
# ---------------------------------------------------------------------------

def rule_d_04_detect_recurrence(ticket):
    """
    Build a stable error signature for this ticket.

    The signature is a sorted set of words from title and description
    longer than three characters, truncated to 160 characters. Sorting
    makes the signature insensitive to word order, so the same fault
    described differently still groups together.

    Writes to rule_results:
        d04_error_signature  (str)
    """
    searchable_text = (
        (ticket.get("title") or "") + " " + (ticket.get("description") or "")
    ).lower()

    unique_tokens = sorted(set(token for token in searchable_text.split() if len(token) > 3))
    signature = " ".join(unique_tokens)[:160]

    ticket["rule_results"]["d04_error_signature"] = signature
    return ticket


# ---------------------------------------------------------------------------
# D-05 Watch who is raising
# ---------------------------------------------------------------------------
# Jira only exposes accountType, not job title, so this rule uses a
# keyword match against the reporter role. If a proper role source is
# added to the pipeline, replace SENIOR_ROLES with that lookup.
# ---------------------------------------------------------------------------

def rule_d_05_watch_who_is_raising(ticket):
    """
    Flag tickets raised by senior client staff.

    A rising share of tickets from senior staff rather than end users is
    an early escalation signal.

    Writes to rule_results:
        d05_senior_raiser  (bool)
    """
    reporter_role = (ticket.get("reporter_role") or "").lower()
    is_senior = (
        reporter_role in SENIOR_ROLES
        or any(senior_keyword in reporter_role for senior_keyword in SENIOR_ROLES)
    )

    ticket["rule_results"]["d05_senior_raiser"] = is_senior
    return ticket


# ---------------------------------------------------------------------------
# D-06 Compare against the client's own baseline
# ---------------------------------------------------------------------------
# The baseline is injected into ticket["client_baseline"] before the
# rules run. This rule only records the comparison.
# ---------------------------------------------------------------------------

def rule_d_06_compare_against_baseline(ticket):
    """
    Record the client baseline attached to this ticket.

    The baseline itself is computed from historical tickets and injected
    by the pipeline. This rule does not compute it.

    Writes to rule_results:
        d06_baseline       (dict)
        d06_has_baseline   (bool)
    """
    baseline = ticket.get("client_baseline") or {}

    ticket["rule_results"]["d06_baseline"] = baseline
    ticket["rule_results"]["d06_has_baseline"] = bool(baseline)
    return ticket


# ---------------------------------------------------------------------------
# D-07 Score and alert
# ---------------------------------------------------------------------------
# Produces the per-ticket contribution to the client health score. The
# aggregator in jira_rule_engine.py sums these per client.
# ---------------------------------------------------------------------------

def rule_d_07_score_and_alert(ticket):
    """
    Compute this ticket's contribution to the client health score.

    Contribution:
        +1 if the ticket was reopened
        +1 if the raiser is senior
        +1 if waiting time exceeds working time

    Writes to rule_results:
        d07_health_contribution  (int)
    """
    rule_results = ticket["rule_results"]
    contribution = 0

    if rule_results.get("d03_has_reopen"):
        contribution += 1
    if rule_results.get("d05_senior_raiser"):
        contribution += 1

    waiting_seconds = rule_results.get("d02_waiting_seconds") or 0
    working_seconds = rule_results.get("d02_working_seconds") or 0

    if working_seconds > 0 and waiting_seconds > working_seconds:
        contribution += 1

    rule_results["d07_health_contribution"] = contribution
    return ticket


RULES = [
    rule_d_01_build_history,
    rule_d_02_separate_waiting_from_working,
    rule_d_03_count_reopens,
    rule_d_04_detect_recurrence,
    rule_d_05_watch_who_is_raising,
    rule_d_06_compare_against_baseline,
    rule_d_07_score_and_alert,
]