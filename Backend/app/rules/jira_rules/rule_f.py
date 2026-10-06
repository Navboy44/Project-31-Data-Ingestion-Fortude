"""
Rule set F: Effort and cost recovery.

Answers the finance question: where did last quarter's consultant time
actually go, and did we recover it?

Rules
-----
F-01  Classify each worklog by effort type
F-02  Score confidence and mark weak classifications as Unknown
F-03  Apply the cost rate for the person's role
F-04  Mark closed-period worklogs for the adjustments stream
F-05  Isolate internal rework hours
F-06  Preserve the evidence behind each classification
F-07  Report total cost and hours on the ticket

Notes
-----
F operates on ticket["worklogs"], not on the ticket itself. It reads the
scope decision produced by rule B, so rule set B must run before F. The
rate table is injected into ticket["rate_table"] before the rules run.
"""

from datetime import datetime


# Confidence below which the classification is discarded in favour of
# "Unknown". Never guess at cost.
F02_CONFIDENCE_THRESHOLD = 0.5

# Policy version recorded in the evidence block so historical
# classifications remain defensible when the policy changes.
F06_POLICY_VERSION = "v1"


def _parse_ts(value):
    """
    Parse a Jira-style ISO 8601 timestamp into a datetime.

    Returns None if the value is missing or unparseable.
    """
    if not value:
        return None

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None


def _is_in_closed_period(started, closed_periods):
    """
    Return True if a worklog start time falls inside a closed period.

    closed_periods is a list of {"start": iso, "end": iso} dicts injected
    by the pipeline. A worklog that falls inside one is routed to the
    adjustments stream rather than modifying the published figure.
    """
    started_at = _parse_ts(started)
    if not started_at or not closed_periods:
        return False

    for period in closed_periods:
        period_start = _parse_ts(period.get("start"))
        period_end = _parse_ts(period.get("end"))
        if period_start and period_end and period_start <= started_at <= period_end:
            return True
    return False


# ---------------------------------------------------------------------------
# F-01 Classify the effort
# ---------------------------------------------------------------------------
# Uses issue_type, parent_project, and the B-02/B-03 scope decision to
# place each worklog into one of five categories. Writes the category
# onto each worklog, not on the ticket.
# ---------------------------------------------------------------------------

def rule_f_01_classify_effort(ticket):
    """
    Classify each worklog by effort type.

    Categories:
        Internal Rework     defect raised against internal work
        Billable Project    has a parent project that is not support
        Contracted Support  live contract and function area in scope
        Out of Scope        live contract and function area not in scope
        Unknown             insufficient evidence to decide

    Writes to each worklog:
        worklog["category"]  (str)
    """
    rule_results = ticket["rule_results"]
    contract_live = rule_results.get("b02_contract_live", False)
    in_scope = rule_results.get("b03_in_scope")
    issue_type = (ticket.get("issue_type") or "").lower()
    parent_project = (ticket.get("parent_project") or "").lower()

    if "defect" in issue_type and "internal" in parent_project:
        category = "Internal Rework"
    elif parent_project and "support" not in parent_project:
        category = "Billable Project"
    elif contract_live and in_scope is True:
        category = "Contracted Support"
    elif contract_live and in_scope is False:
        category = "Out of Scope"
    else:
        category = "Unknown"

    for worklog in ticket.get("worklogs", []):
        worklog["category"] = category

    return ticket


# ---------------------------------------------------------------------------
# F-02 Score the confidence
# ---------------------------------------------------------------------------
# Confidence is based on how much of the classification evidence exists.
# Anything below the threshold becomes Unknown, never a guess.
# ---------------------------------------------------------------------------

def rule_f_02_score_confidence(ticket):
    """
    Score classification confidence and downgrade weak ones to Unknown.

    Confidence is the fraction of three signals present:
        ticket_key, parent_project, contract

    Any worklog whose confidence is below F02_CONFIDENCE_THRESHOLD is
    re-classified as Unknown. Guessing produces numbers that cannot be
    defended.

    Writes to each worklog:
        worklog["confidence"]  (float)
        worklog["category"]    (may be overwritten to "Unknown")
    """
    has_ticket_key = bool(ticket.get("ticket_key"))
    has_parent_project = bool(ticket.get("parent_project"))
    has_contract = bool(ticket.get("contract"))

    confidence_score = sum([has_ticket_key, has_parent_project, has_contract]) / 3

    for worklog in ticket.get("worklogs", []):
        worklog["confidence"] = round(confidence_score, 2)
        if confidence_score < F02_CONFIDENCE_THRESHOLD:
            worklog["category"] = "Unknown"

    return ticket


# ---------------------------------------------------------------------------
# F-03 Apply the right rate
# ---------------------------------------------------------------------------
# The rate table is injected into ticket["rate_table"]. Historical rates
# are preserved by keying on the worklog's author role rather than a
# current table.
# ---------------------------------------------------------------------------

def rule_f_03_apply_cost_rate(ticket):
    """
    Compute the cost of each worklog from the injected rate table.

    rate_table is a dict keyed by role, with an optional "default" entry.

    Writes to each worklog:
        worklog["role"]  (str)
        worklog["rate"]  (float)
        worklog["cost"]  (float)
    """
    rate_table = ticket.get("rate_table") or {}
    default_rate = rate_table.get("default", 0)

    for worklog in ticket.get("worklogs", []):
        role = worklog.get("author_role") or "Consultant"
        rate = rate_table.get(role, default_rate)
        hours = (worklog.get("time_spent_seconds") or 0) / 3600

        worklog["role"] = role
        worklog["rate"] = rate
        worklog["cost"] = round(hours * rate, 2)

    return ticket


# ---------------------------------------------------------------------------
# F-04 Never edit a published figure
# ---------------------------------------------------------------------------
# Worklogs in closed periods are marked for the adjustments stream. The
# rule does not modify or delete the original figures.
# ---------------------------------------------------------------------------

def rule_f_04_never_edit_published(ticket):
    """
    Mark each worklog as append-only and route closed-period ones to the
    adjustments stream.

    Writes to each worklog:
        worklog["append_only"]        (bool)
        worklog["is_closed_period"]   (bool)
        worklog["stream"]             (str)
    """
    closed_periods = ticket.get("closed_periods") or []

    for worklog in ticket.get("worklogs", []):
        worklog["append_only"] = True
        worklog["is_closed_period"] = _is_in_closed_period(
            worklog.get("started"), closed_periods
        )
        worklog["stream"] = "adjustment" if worklog["is_closed_period"] else "current"

    return ticket


# ---------------------------------------------------------------------------
# F-05 Isolate rework
# ---------------------------------------------------------------------------

def rule_f_05_isolate_rework(ticket):
    """
    Sum the hours spent on internal rework.

    Internal rework is effort spent fixing defects the consultancy
    introduced. It is the number most worth reducing and the one most
    often hidden inside general support.

    Writes to rule_results:
        f05_rework_hours  (float)
    """
    rework_hours = 0

    for worklog in ticket.get("worklogs", []):
        if worklog.get("category") == "Internal Rework":
            rework_hours += (worklog.get("time_spent_seconds") or 0) / 3600

    ticket["rule_results"]["f05_rework_hours"] = round(rework_hours, 2)
    return ticket


# ---------------------------------------------------------------------------
# F-06 Keep the evidence
# ---------------------------------------------------------------------------

def rule_f_06_keep_evidence(ticket):
    """
    Record the inputs and policy version behind the classification.

    This makes the numbers defensible when finance or audit asks why a
    worklog was classified a particular way.

    Writes to rule_results:
        f06_evidence  (dict)
    """
    rule_results = ticket["rule_results"]

    rule_results["f06_evidence"] = {
        "policy_version": F06_POLICY_VERSION,
        "inputs": {
            "b02_contract_live": rule_results.get("b02_contract_live"),
            "b03_in_scope": rule_results.get("b03_in_scope"),
            "issue_type": ticket.get("issue_type"),
            "parent_project": ticket.get("parent_project"),
        },
        "rules_applied": [
            rule_name for rule_name in rule_results.get("rules_applied", [])
            if rule_name.startswith("rule_f_")
        ],
        "evaluated_at": rule_results.get("rules_evaluated_at"),
    }

    return ticket


# ---------------------------------------------------------------------------
# F-07 Report margin per client
# ---------------------------------------------------------------------------
# Per ticket it writes total cost and total hours. The aggregator in
# jira_rule_engine.py sums these by client and contract.
# ---------------------------------------------------------------------------

def rule_f_07_report_margin(ticket):
    """
    Sum cost and hours for all worklogs on the ticket.

    Writes to rule_results:
        f07_total_cost   (float)
        f07_total_hours  (float)
    """
    total_cost = sum((worklog.get("cost") or 0) for worklog in ticket.get("worklogs", []))
    total_hours = sum(
        (worklog.get("time_spent_seconds") or 0) for worklog in ticket.get("worklogs", [])
    ) / 3600

    ticket["rule_results"]["f07_total_cost"] = round(total_cost, 2)
    ticket["rule_results"]["f07_total_hours"] = round(total_hours, 2)
    return ticket


RULES = [
    rule_f_01_classify_effort,
    rule_f_02_score_confidence,
    rule_f_03_apply_cost_rate,
    rule_f_04_never_edit_published,
    rule_f_05_isolate_rework,
    rule_f_06_keep_evidence,
    rule_f_07_report_margin,
]