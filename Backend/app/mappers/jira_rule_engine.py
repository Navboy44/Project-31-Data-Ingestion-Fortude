"""
Rule engine for canonical Jira tickets.

This module is the only place that decides *which* rules run and *when*.
The rules themselves live under the `rules` package. The engine:

1. Resolves a rule set name ("A", "B", "ALL", ...) to a list of rules.
2. Applies each rule to each ticket and records what ran and what failed.
3. Runs cross-ticket aggregators (D, B, F) after per-ticket rules.

Design principles
-----------------
- Rules are pure functions: ticket in, ticket out.
- Rule outputs go into ticket["rules_results"], never onto Jira's own fields.
- Every rule's execution is recorded in rules_results["rules_applied"].
- Errors are captured per rule, not per ticket, so one bad rule cannot
  discard the work of the others.
- Aggregators are separate because they need to see many tickets at once.
"""

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from app.rules.jira_rules import RULE_SETS, DEFAULT_RULE_SET, ALL_RULE_ORDER


class RuleEngineError(Exception):
    """Raised when a rule set name is unknown or cannot be resolved."""
    pass


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def _now_iso():
    """Return the current zone time as an ISO 8601 string."""
    return datetime.now(ZoneInfo("Australia/Melbourne")).isoformat()


def _parse_ts(value):
    """
    Parse a Jira-style timestamp into a datetime.

    Returns None if the value is missing or unparseable. Callers use this
    to compare ticket times against aggregation windows.
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
# Rule set resolution
# ---------------------------------------------------------------------------

def _resolve_rule_set(rule_set_name):
    """
    Normalise a rule set name to a canonical value.

    - Empty / None falls back to DEFAULT_RULE_SET (usually "ALL").
    - "L3 Ticket Rules" is kept as an alias for "A" so older callers
      continue to work without change.
    """
    if not rule_set_name:
        return DEFAULT_RULE_SET
    if rule_set_name == "L3 Ticket Rules":
        return "A"
    return rule_set_name


# ---------------------------------------------------------------------------
# Per-ticket rule application
# ---------------------------------------------------------------------------

def apply_rule_set(ticket, rule_set_name, stop_on_error=False):
    """
    Apply every rule in a rule set to one ticket.

    Args:
        ticket: A canonical ticket dict.
        rule_set_name: One of "A", "B", "C", "D", "F", "G", "ALL".
        stop_on_error: If True, re-raise on the first rule failure instead
            of recording the error and continuing.

    Returns:
        The same ticket with rule output merged into ticket["rule_results"].

    Side effects:
        Appends executed rule names to rule_results["rules_applied"].
        Appends per-rule failures to rule_results["rule_errors"].
        Records the rule set name and evaluation time.
    """
    # _resolve_rule_set returns a *name* ("A", "B", ..., "ALL"),
    # not a list of rules. Use it to look up the rules in RULE_SETS.
    resolved_name = _resolve_rule_set(rule_set_name)
    rules = RULE_SETS.get(resolved_name)

    if rules is None:
        raise RuleEngineError(f"Unknown rule set: {resolved_name}")

    ticket.setdefault("rule_results", {})
    ticket["rule_results"].setdefault("rules_applied", [])
    ticket["rule_results"].setdefault("rule_errors", [])

    for rule in rules:
        rule_name = getattr(rule, "__name__", str(rule))
        try:
            ticket = rule(ticket)
            ticket["rule_results"]["rules_applied"].append(rule_name)
        except Exception as exception:
            # Record the failure but do not stop the ticket from being
            # processed by the remaining rules.
            ticket["rule_results"]["rule_errors"].append({
                "rule": rule_name,
                "error": str(exception),
            })
            if stop_on_error:
                raise

    ticket["rule_results"]["rule_set"] = resolved_name
    ticket["rule_results"]["rules_evaluated_at"] = _now_iso()
    return ticket


def transform_tickets(tickets, rule_set_name, stop_on_error=False):
    """
    Apply one rule set to a list of tickets.

    Returns a new list in the same order as the input.
    """
    return [
        apply_rule_set(ticket, rule_set_name, stop_on_error=stop_on_error)
        for ticket in tickets
    ]


def transform_canonical_tickets(tickets, rule_set_name=None):
    """
    Per-ticket rule entry point.

    Args:
        tickets: List of canonical tickets.
        rule_set_name: "A", "B", "C", "D", "F", "G", or "ALL".
            None or empty defaults to "ALL".
            "L3 Ticket Rules" is accepted as an alias for "A".

    Returns:
        The same list with each ticket enriched by the rules.

    Behaviour:
        "ALL" runs every rule set in ALL_RULE_ORDER. The order matters:
        A must run before B, F, and G because those rules read the
        severity and function classification A produces.
    """
    rule_set_name = _resolve_rule_set(rule_set_name)

    if rule_set_name == "ALL":
        for name in ALL_RULE_ORDER:
            tickets = transform_tickets(tickets, name)
        # Record the effective rule set on every ticket, overwriting the
        # per-set label written by the last apply_rule_set call.
        for ticket in tickets:
            ticket.setdefault("rule_results", {})
            ticket["rule_results"]["rule_set"] = "ALL"
        return tickets

    if rule_set_name not in RULE_SETS:
        raise RuleEngineError(f"Unknown rule set: {rule_set_name}")

    return transform_tickets(tickets, rule_set_name)


# ---------------------------------------------------------------------------
# Cross-ticket aggregations
# ---------------------------------------------------------------------------
# Aggregators cannot run per ticket because they need to see many tickets
# at once (client baselines, recurrence over time, totals per client).
# They run after the per-ticket rules and write into ticket["rule_results"].

def _group_by(tickets, key_fn):
    """
    Group tickets into a dict keyed by key_fn(ticket).

    Tickets for which key_fn returns None are skipped. This lets callers
    use a group key that may be missing on some tickets (for example
    client_id before it has been mapped).
    """
    groups = {}
    for ticket in tickets:
        key = key_fn(ticket)
        if key is None:
            continue
        groups.setdefault(key, []).append(ticket)
    return groups


# --------------------------- D: client health -----------------------------

def aggregate_recurrence(tickets):
    """
    Detect recurring faults across tickets (rule D-04).

    A pattern exists when the same client raises the same fault signature
    in the same function area three or more times within 90 days.

    Writes to each affected ticket:
        rule_results.d04_recurrence_pattern      (bool)
        rule_results.d04_recurrence_count_90d    (int)
    """
    cutoff = datetime.now(ZoneInfo("Australia/Melbourne")) - timedelta(days=90)

    grouped = _group_by(
        tickets,
        lambda ticket: (
            ticket.get("client_id"),
            ticket.get("function_area"),
            ticket.get("rule_results", {}).get("d04_error_signature"),
        ),
    )

    for _, group in grouped.items():
        recent = [
            ticket for ticket in group
            if (
                _parse_ts(ticket.get("created_at"))
                or datetime.min.replace(tzinfo=timezone.utc)
            ) >= cutoff
        ]

        is_pattern = len(recent) >= 3
        for ticket in group:
            ticket.setdefault("rule_results", {})
            ticket["rule_results"]["d04_recurrence_pattern"] = is_pattern
            ticket["rule_results"]["d04_recurrence_count_90d"] = len(recent)

    return tickets


def aggregate_client_health(tickets):
    """
    Compute a health score per client (rules D-06 and D-07).

    The score is the average of each ticket's contribution to health.
    Comparison against a client-specific baseline is done by rule D-06
    using the injected client_baseline field; this aggregator only
    produces the raw per-client score.

    Writes to each affected ticket:
        rule_results.d07_client_health_score  (float)
        rule_results.d07_client_alert         (bool)
    """
    grouped = _group_by(tickets, lambda ticket: ticket.get("client_id"))

    for _, group in grouped.items():
        total = sum(
            ticket.get("rule_results", {}).get("d07_health_contribution", 0)
            for ticket in group
        )
        score = total / len(group) if group else 0

        for ticket in group:
            ticket.setdefault("rule_results", {})
            ticket["rule_results"]["d07_client_health_score"] = round(score, 2)
            ticket["rule_results"]["d07_client_alert"] = score >= 2

    return tickets


# --------------------------- B: leakage -----------------------------------

def aggregate_leakage(tickets):
    """
    Sum out-of-scope hours per client and function area (rule B-07).

    Writes to each affected ticket:
        rule_results.b07_client_function_leakage_hours  (float)
    """
    grouped = _group_by(
        tickets,
        lambda ticket: (ticket.get("client_id"), ticket.get("function_area")),
    )

    for _, group in grouped.items():
        total_hours = sum(
            ticket.get("rule_results", {}).get("b07_leakage_hours", 0)
            for ticket in group
        )
        for ticket in group:
            ticket.setdefault("rule_results", {})
            ticket["rule_results"]["b07_client_function_leakage_hours"] = round(total_hours, 2)

    return tickets


# --------------------------- F: margin ------------------------------------

def aggregate_margin(tickets):
    """
    Sum effort cost per client and contract (rule F-07).

    Writes to each affected ticket:
        rule_results.f07_client_contract_cost  (float)
    """
    grouped = _group_by(
        tickets,
        lambda ticket: (ticket.get("client_id"), ticket.get("contract_id")),
    )

    for _, group in grouped.items():
        total_cost = sum(
            ticket.get("rule_results", {}).get("f07_total_cost", 0)
            for ticket in group
        )
        for ticket in group:
            ticket.setdefault("rule_results", {})
            ticket["rule_results"]["f07_client_contract_cost"] = round(total_cost, 2)

    return tickets


# Registry: which aggregators run for which rule set.
AGGREGATORS = {
    "D": [aggregate_recurrence, aggregate_client_health],
    "B": [aggregate_leakage],
    "F": [aggregate_margin],
}


def run_aggregators(tickets, rule_set_name=None):
    """
    Run every aggregator associated with a rule set.

    For "ALL", runs the aggregators for every rule set in ALL_RULE_ORDER
    in the same order. Returns the modified ticket list.
    """
    rule_set_name = _resolve_rule_set(rule_set_name)

    if rule_set_name == "ALL":
        for name in ALL_RULE_ORDER:
            for aggregator in AGGREGATORS.get(name, []):
                tickets = aggregator(tickets)
        return tickets

    for aggregator in AGGREGATORS.get(rule_set_name, []):
        tickets = aggregator(tickets)
    return tickets


# ---------------------------------------------------------------------------
# Combined entry points
# ---------------------------------------------------------------------------

def transform_canonical_tickets_full(tickets, rule_set_name=None):
    """
    Full pipeline entry point: per-ticket rules then cross-ticket aggregators.

    Use this from the pollers and the full sync. It is the only function
    callers need in order to run the whole rule engine on a batch of
    canonical tickets.

    Args:
        tickets: List of canonical tickets.
        rule_set_name: "A", "B", "C", "D", "F", "G", or "ALL".
            None or empty defaults to "ALL".
    """
    rule_set_name = _resolve_rule_set(rule_set_name)
    tickets = transform_canonical_tickets(tickets, rule_set_name)
    tickets = run_aggregators(tickets, rule_set_name)
    return tickets