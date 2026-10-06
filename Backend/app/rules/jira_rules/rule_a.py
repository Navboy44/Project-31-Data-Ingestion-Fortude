"""
Rule set A: Ticket triage and SLA integrity.

Answers the support desk question: is the right ticket being worked on
first, and do our SLA numbers mean anything?

Rules
-----
A-01  Validate on arrival
A-02  Classify the function area
A-03  Send low confidence classifications to a human
A-04  Derive severity from evidence, not from the client's claim
A-05  Apply context modifiers (non-production cap, period-close raise)
A-06  Record the gap between claimed and derived severity
A-07  Run an honest SLA clock against tier and elapsed time
A-08  Route to a skill pool and decide on escalation

Dependencies
------------
A must run before B, C, D, F, and G, because those rule sets read
ticket["function_area"] and ticket["rule_results"]["a04_severity"].
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


# Severity ladder used by A-04, A-05, and A-06 to compare levels.
SEVERITY_LEVELS = {"Low": 0, "Medium": 1, "High": 2, "Critical": 3}

# Keyword map for A-02. The lookup order is documented in the rule itself:
# M3 program code first, then keywords, then the reporter's department.
FUNCTION_KEYWORDS = {
    "Finance": ["invoice", "finance", "gl ", "ledger", "payment", "accounting"],
    "Warehouse": ["warehouse", "inventory", "stock", "pick", "putaway"],
    "Order": ["order", "purchase", "sales order", "delivery", "shipment"],
    "Production": ["production", "manufacturing", "work order", "assembly", "quality"],
    "HR": ["employee", "payroll", "hr ", "absence"],
}

# Ordered severity ladder used by A-05 when raising a Finance ticket
# during the client's period-close window.
SEVERITY_ORDER = ["Low", "Medium", "High", "Critical"]


def _parse_ts(value):
    """
    Parse a Jira-style ISO 8601 timestamp into a datetime.

    Jira returns timestamps with or without microseconds. Both formats are
    attempted. Returns None if the value is missing or unparseable.
    """
    if not value:
        return None

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None


# ---------------------------------------------------------------------------
# A-01 Validate on arrival
# ---------------------------------------------------------------------------
# Reads the mandatory fields the mapper produced. It does not delete the
# ticket from the pipeline - it only marks it as incomplete so a downstream
# writer can route it to the clarification queue.
# ---------------------------------------------------------------------------

def rule_a_01_validate_on_arrival(ticket):
    """
    Check that the ticket has the fields required for triage.

    Does not reject the ticket. Records the missing field names so a
    downstream writer can route it to a clarification queue. The ticket
    continues through the remaining rules so nothing is lost.

    Writes to rule_results:
        a01_missing_fields  (list[str])
        a01_valid           (bool)
    """
    missing_fields = []

    if not ticket.get("ticket_key"):
        missing_fields.append("ticket_key")
    if not ticket.get("description"):
        missing_fields.append("description")
    if not ticket.get("created_at"):
        missing_fields.append("created_at")
    if not ticket.get("client_id"):
        missing_fields.append("client_id")
    if not ticket.get("environment"):
        missing_fields.append("environment")

    ticket["rule_results"]["a01_missing_fields"] = missing_fields
    ticket["rule_results"]["a01_valid"] = len(missing_fields) == 0
    return ticket


# ---------------------------------------------------------------------------
# A-02 Classify the function
# ---------------------------------------------------------------------------
# Priority order matches the design doc:
#   1. M3 program code (highest confidence)
#   2. Keyword match against title and description
#   3. The reporter's department (lowest confidence)
# The chosen source and a confidence score are recorded so downstream
# rules can decide whether the classification is trustworthy.
# ---------------------------------------------------------------------------

def rule_a_02_classify_function(ticket):
    """
    Classify the ticket into a function area.

    Priority order:
        1. M3 program code (confidence 0.95)
        2. Keywords in title and description (confidence 0.70)
        3. Reporter's department (confidence 0.50)

    Writes:
        ticket["function_area"]                     (str | None)
        rule_results["a02_confidence"]              (float)
        rule_results["a02_source"]                  (str | None)
    """
    function_area = None
    confidence = 0.0
    classification_source = None

    if ticket.get("m3_program_code"):
        function_area = ticket["m3_program_code"]
        confidence = 0.95
        classification_source = "m3_program_code"
    else:
        searchable_text = (
            (ticket.get("title") or "") + " " + (ticket.get("description") or "")
        ).lower()

        for area, keywords in FUNCTION_KEYWORDS.items():
            if any(keyword in searchable_text for keyword in keywords):
                function_area = area
                confidence = 0.7
                classification_source = "keywords"
                break

        if not function_area:
            reporter_department = ticket.get("reporter_department")
            if reporter_department:
                function_area = reporter_department
                confidence = 0.5
                classification_source = "reporter_department"

    ticket["function_area"] = function_area
    ticket["rule_results"]["a02_confidence"] = confidence
    ticket["rule_results"]["a02_source"] = classification_source
    return ticket


# ---------------------------------------------------------------------------
# A-03 Send low confidence to a human
# ---------------------------------------------------------------------------
# The rule does not clear function_area. It only flags that a human must
# confirm it. The original classification is preserved for analytics.
# ---------------------------------------------------------------------------

A02_CONFIDENCE_THRESHOLD = 0.6


def rule_a_03_send_low_confidence_to_human(ticket):
    """
    Flag tickets whose function classification is not trustworthy.

    Low-confidence tickets go to human triage instead of being assigned
    a function automatically. The classification itself is kept so that
    reporting and later analytics still see it.

    Writes to rule_results:
        a03_needs_triage           (bool)
        a03_confidence_threshold   (float)
    """
    confidence = ticket["rule_results"].get("a02_confidence", 0)
    needs_triage = confidence < A02_CONFIDENCE_THRESHOLD

    ticket["rule_results"]["a03_needs_triage"] = needs_triage
    ticket["rule_results"]["a03_confidence_threshold"] = A02_CONFIDENCE_THRESHOLD
    return ticket


# ---------------------------------------------------------------------------
# A-04 Derive severity
# ---------------------------------------------------------------------------
# Scores business impact, user impact, and workaround availability.
# The client's claimed priority is recorded alongside the derived value
# so A-06 can measure the gap. The claim is never used to compute the
# derived severity itself.
# ---------------------------------------------------------------------------

def rule_a_04_derive_severity(ticket):
    """
    Compute severity from ticket evidence.

    Scoring:
        +2 for outage, production down, system down
        +3 for data loss, breach, security
        +2 for all users, everyone, company wide
        +1 for cannot work, blocked, no workaround
        -1 if a workaround is mentioned

    Bands:
        score >= 4  -> Critical
        score >= 2  -> High
        score >= 1  -> Medium
        otherwise   -> Low

    Writes to rule_results:
        a04_severity           (str)
        a04_claimed_severity   (str | None)  from the ticket's priority
        a04_score              (int)
    """
    searchable_text = (
        (ticket.get("title") or "") + " " + (ticket.get("description") or "")
    ).lower()

    impact_score = 0

    if any(keyword in searchable_text for keyword in ("outage", "production down", "system down")):
        impact_score += 2
    if any(keyword in searchable_text for keyword in ("data loss", "breach", "security")):
        impact_score += 3
    if any(keyword in searchable_text for keyword in ("all users", "everyone", "company wide")):
        impact_score += 2
    if any(keyword in searchable_text for keyword in ("cannot work", "blocked", "no workaround")):
        impact_score += 1
    if "workaround" in searchable_text:
        impact_score -= 1

    if impact_score >= 4:
        severity_label = "Critical"
    elif impact_score >= 2:
        severity_label = "High"
    elif impact_score >= 1:
        severity_label = "Medium"
    else:
        severity_label = "Low"

    ticket["rule_results"]["a04_severity"] = severity_label
    ticket["rule_results"]["a04_claimed_severity"] = ticket.get("priority")
    ticket["rule_results"]["a04_score"] = impact_score
    return ticket


# ---------------------------------------------------------------------------
# A-05 Apply context modifiers
# ---------------------------------------------------------------------------
# Caps non-production severity unless a go-live is imminent, and raises
# Finance tickets during the client's period-close window. Both flags are
# injected by the pipeline before the rules run; they do not come from
# Jira itself.
# ---------------------------------------------------------------------------

def rule_a_05_apply_context_modifiers(ticket):
    """
    Adjust severity based on environment and business context.

    Modifiers applied in order:
        1. Cap severity to Medium for non-production tickets, unless a
           go-live is imminent (ticket["go_live_imminent"]).
        2. Raise Finance tickets one level during the client's
           period-close window (ticket["client_period_close"]).

    Writes to rule_results:
        a04_severity         (modified in place)
        a05_modified         (bool)
        a05_cap_reason       (str)  only when a cap was applied
        a05_raise_reason     (str)  only when a raise was applied
    """
    rule_results = ticket["rule_results"]
    severity = rule_results.get("a04_severity")
    environment = (ticket.get("environment") or "").lower()
    go_live_imminent = bool(ticket.get("go_live_imminent"))
    period_close = bool(ticket.get("client_period_close"))
    function_area = ticket.get("function_area")

    modified = False

    # Non-production tickets are capped unless a go-live is imminent.
    if "production" not in environment and not go_live_imminent:
        if severity in ("Critical", "High"):
            rule_results["a04_severity"] = "Medium"
            modified = True
            rule_results["a05_cap_reason"] = "non_production"

    # Finance tickets are raised one level during period close.
    if function_area == "Finance" and period_close:
        current_severity = rule_results.get("a04_severity")
        if current_severity in SEVERITY_ORDER and current_severity != "Critical":
            next_index = SEVERITY_ORDER.index(current_severity) + 1
            rule_results["a04_severity"] = SEVERITY_ORDER[next_index]
            modified = True
            rule_results["a05_raise_reason"] = "period_close"

    rule_results["a05_modified"] = modified
    return ticket


# ---------------------------------------------------------------------------
# A-06 Record the disagreement
# ---------------------------------------------------------------------------
# Where the derived and claimed severities differ by more than one level,
# keep both and flag it. The flag is a relationship signal, not a rule
# failure.
# ---------------------------------------------------------------------------

def rule_a_06_record_disagreement(ticket):
    """
    Compare the client's claimed severity against the derived severity.

    A gap larger than one level is flagged. The gap is preserved as a
    numeric value so downstream reporting can trend it per client.

    Writes to rule_results:
        a06_severity_disagreement  (bool)
        a06_severity_gap           (int | None)
    """
    claimed_severity = ticket["rule_results"].get("a04_claimed_severity")
    derived_severity = ticket["rule_results"].get("a04_severity")

    if claimed_severity not in SEVERITY_LEVELS or derived_severity not in SEVERITY_LEVELS:
        ticket["rule_results"]["a06_severity_disagreement"] = False
        ticket["rule_results"]["a06_severity_gap"] = None
        return ticket

    gap = abs(SEVERITY_LEVELS[claimed_severity] - SEVERITY_LEVELS[derived_severity])

    ticket["rule_results"]["a06_severity_disagreement"] = gap > 1
    ticket["rule_results"]["a06_severity_gap"] = gap
    return ticket


# ---------------------------------------------------------------------------
# A-07 Run an honest clock
# ---------------------------------------------------------------------------
# Measures elapsed hours against the tier's SLA and computes breach risk
# as a 0.0 - 1.0 score. Only the elapsed time from creation to now is
# considered here; calendar-aware pausing is a downstream concern.
# ---------------------------------------------------------------------------

def rule_a_07_run_sla_clock(ticket):
    """
    Compute SLA hours, elapsed time, and a breach-risk score.

    SLA hours depend on the customer tier:
        Enterprise -> 4 hours
        everything else -> 24 hours

    Breach risk is elapsed / SLA, capped at 1.0. A value of 1.0 means
    the ticket has reached or passed its SLA.

    Writes to rule_results:
        a07_sla_hours             (int)
        a07_hours_since_created   (float)
        a07_breach_risk_score     (float)
        a07_breached              (bool)
    """
    tier = str(ticket.get("customer_tier") or "").lower()
    sla_hours = 4 if tier == "enterprise" else 24

    created = _parse_ts(ticket.get("created_at"))
    now = datetime.now(ZoneInfo("Australia/Melbourne"))

    hours_since_created = 0.0
    if created:
        hours_since_created = round((now - created).total_seconds() / 3600, 2)

    breach_risk_score = 0.0
    if sla_hours > 0:
        breach_risk_score = round(min(hours_since_created / sla_hours, 1.0), 2)

    ticket["rule_results"]["a07_sla_hours"] = sla_hours
    ticket["rule_results"]["a07_hours_since_created"] = hours_since_created
    ticket["rule_results"]["a07_breach_risk_score"] = breach_risk_score
    ticket["rule_results"]["a07_breached"] = hours_since_created > sla_hours
    return ticket


# ---------------------------------------------------------------------------
# A-08 Route and escalate
# ---------------------------------------------------------------------------
# Assigns a skill pool from the function area, then decides whether the
# duty manager gets paged. Only genuine top severity or high breach risk
# triggers a page.
# ---------------------------------------------------------------------------

SKILL_POOL_BY_FUNCTION = {
    "Finance": "finance_support",
    "Warehouse": "warehouse_support",
    "Order": "order_support",
    "Production": "production_support",
    "HR": "hr_support",
}


def rule_a_08_route_and_escalate(ticket):
    """
    Choose a skill pool and decide escalation.

    Routing:
        function_area -> skill pool, or "general_support" if unknown.

    Escalation:
        Critical severity                    -> IMMEDIATE, page on-call
        High severity AND breach risk >= 0.75 -> HIGH, page on-call
        Any severity with breach risk >= 0.75 -> HIGH, no page
        Otherwise                             -> NORMAL

    Writes to rule_results:
        a08_skill_pool         (str)
        a08_escalation_level   (str)
        a08_page_on_call       (bool)
    """
    rule_results = ticket["rule_results"]
    severity = rule_results.get("a04_severity")
    breach_risk = rule_results.get("a07_breach_risk_score", 0)
    function_area = ticket.get("function_area")

    skill_pool = SKILL_POOL_BY_FUNCTION.get(function_area, "general_support")

    escalation_level = "NORMAL"
    page_on_call = False

    if severity == "Critical":
        escalation_level = "IMMEDIATE"
        page_on_call = True
    elif severity == "High" and breach_risk >= 0.75:
        escalation_level = "HIGH"
        page_on_call = True
    elif breach_risk >= 0.75:
        escalation_level = "HIGH"

    rule_results["a08_skill_pool"] = skill_pool
    rule_results["a08_escalation_level"] = escalation_level
    rule_results["a08_page_on_call"] = page_on_call
    return ticket


RULES = [
    rule_a_01_validate_on_arrival,
    rule_a_02_classify_function,
    rule_a_03_send_low_confidence_to_human,
    rule_a_04_derive_severity,
    rule_a_05_apply_context_modifiers,
    rule_a_06_record_disagreement,
    rule_a_07_run_sla_clock,
    rule_a_08_route_and_escalate,
]