"""
Rule set B: Contract scope and revenue leakage.

Answers the account management question: how much work are we doing for
free?

Rules
-----
B-02  Check the contract is live on the ticket date
B-03  Check the ticket's function area is covered by the contract
B-04  Route out-of-scope work to a billable path instead of absorbing it
B-05  Warn when entitlement consumption reaches a threshold
B-06  Flag contracts approaching expiry
B-07  Record leakage hours per ticket (aggregated later by the engine)

Dependencies
------------
B reads ticket["contract"], which is injected by the pipeline before the
rules run. It also reads function_area and a02_confidence from rule A.
"""

from datetime import datetime


# Consumption ratio at which the account manager is warned, before the
# retainer is fully exhausted.
B05_THRESHOLD = 0.8

# Number of days before contract end date at which B-06 flags the contract
# as expiring soon.
B06_WINDOW_DAYS = 60


def _parse_date(value):
    """
    Parse the date part of an ISO 8601 timestamp into a date object.

    Contract dates are stored as YYYY-MM-DD strings. Returns None if the
    value is missing or unparseable, so callers can treat "no date" and
    "invalid date" the same way.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# B-02 Check the contract is live
# ---------------------------------------------------------------------------

def rule_b_02_check_contract_is_live(ticket):
    """
    Determine whether a live contract covers the ticket's date.

    A contract is live if:
        - ticket["contract"] is present
        - the ticket was created on or after the contract start date
        - the ticket was created on or before the contract end date
        - either date may be missing, in which case that bound is ignored

    Writes to rule_results:
        b02_contract_live  (bool)
        b02_contract_id    (str | None)
    """
    contract = ticket.get("contract") or {}
    ticket_date = _parse_date(ticket.get("created_at"))

    start_date = _parse_date(contract.get("start_date"))
    end_date = _parse_date(contract.get("end_date"))

    is_live = (
        bool(contract)
        and ticket_date is not None
        and (start_date is None or start_date <= ticket_date)
        and (end_date is None or end_date >= ticket_date)
    )

    ticket["rule_results"]["b02_contract_live"] = is_live
    ticket["rule_results"]["b02_contract_id"] = contract.get("contract_id")
    return ticket


# ---------------------------------------------------------------------------
# B-03 Check module coverage
# ---------------------------------------------------------------------------
# Uses the function_area produced by A-02. If A-02 was low confidence,
# coverage cannot be trusted, so it is marked unknown instead of False.
# That distinction matters: unknown routes to commercial review, while
# False routes to a billable path.
# ---------------------------------------------------------------------------

def rule_b_03_check_module_coverage(ticket):
    """
    Check whether the ticket's function area is covered by the contract.

    Returns three states:
        True   in scope
        False  explicitly not in scope
        None   coverage cannot be determined (low A-02 confidence)

    Writes to rule_results:
        b03_in_scope         (bool | None)
        b03_covered_modules  (list[str])
    """
    contract = ticket.get("contract") or {}
    covered_modules = [module.lower() for module in (contract.get("covered_modules") or [])]
    function_area = ticket.get("function_area")
    classification_confidence = ticket["rule_results"].get("a02_confidence", 0)

    if not function_area or classification_confidence < 0.6:
        in_scope = None
    else:
        in_scope = function_area.lower() in covered_modules

    ticket["rule_results"]["b03_in_scope"] = in_scope
    ticket["rule_results"]["b03_covered_modules"] = contract.get("covered_modules") or []
    return ticket


# ---------------------------------------------------------------------------
# B-04 Route rather than reject
# ---------------------------------------------------------------------------
# Out-of-scope work goes to a billable path with an estimate requirement.
# It is never silently absorbed and never refused, because refusing
# damages the relationship and absorbing damages the margin.
# ---------------------------------------------------------------------------

def rule_b_04_route_out_of_scope(ticket):
    """
    Choose a routing path for the ticket based on scope.

    Routing rules:
        no live contract        -> billable_path
        in_scope is False       -> billable_path
        in_scope is None        -> commercial_review
        in_scope is True        -> support_queue

    billable_path tickets require an estimate. Support queue tickets do not.

    Writes to rule_results:
        b04_route              (str)
        b04_route_reason       (str)
        b04_requires_estimate  (bool)
    """
    rule_results = ticket["rule_results"]
    contract_live = rule_results.get("b02_contract_live")
    in_scope = rule_results.get("b03_in_scope")

    if not contract_live:
        route = "billable_path"
        route_reason = "no_live_contract"
    elif in_scope is False:
        route = "billable_path"
        route_reason = "module_not_covered"
    elif in_scope is None:
        route = "commercial_review"
        route_reason = "coverage_unknown"
    else:
        route = "support_queue"
        route_reason = "in_scope"

    rule_results["b04_route"] = route
    rule_results["b04_route_reason"] = route_reason
    rule_results["b04_requires_estimate"] = route == "billable_path"
    return ticket


# ---------------------------------------------------------------------------
# B-05 Watch the balance
# ---------------------------------------------------------------------------
# Tracks the ratio of consumed hours to entitled hours. The threshold is
# set to warn before exhaustion so the account manager has time to act.
# ---------------------------------------------------------------------------

def rule_b_05_watch_entitlement_balance(ticket):
    """
    Report entitlement consumption and warn at the threshold.

    Writes to rule_results:
        b05_remaining_hours      (float)
        b05_consumption_ratio    (float)
        b05_threshold_breached   (bool)
    """
    contract = ticket.get("contract") or {}
    entitled_hours = contract.get("entitled_hours") or 0
    consumed_hours = contract.get("consumed_hours") or 0

    consumption_ratio = (consumed_hours / entitled_hours) if entitled_hours else 0

    ticket["rule_results"]["b05_remaining_hours"] = round(entitled_hours - consumed_hours, 2)
    ticket["rule_results"]["b05_consumption_ratio"] = round(consumption_ratio, 2)
    ticket["rule_results"]["b05_threshold_breached"] = consumption_ratio >= B05_THRESHOLD
    return ticket


# ---------------------------------------------------------------------------
# B-06 Track expiry
# ---------------------------------------------------------------------------
# Flags contracts whose end date is within B06_WINDOW_DAYS of the ticket
# date, so renewal becomes a planned conversation rather than a surprise.
# ---------------------------------------------------------------------------

def rule_b_06_track_contract_expiry(ticket):
    """
    Report days to contract expiry and whether it is approaching.

    Writes to rule_results:
        b06_days_to_expiry   (int | None)
        b06_expiring_soon    (bool)
    """
    contract = ticket.get("contract") or {}
    end_date = _parse_date(contract.get("end_date"))
    ticket_date = _parse_date(ticket.get("created_at"))

    if not end_date or not ticket_date:
        ticket["rule_results"]["b06_days_to_expiry"] = None
        ticket["rule_results"]["b06_expiring_soon"] = False
        return ticket

    days_to_expiry = (end_date - ticket_date).days
    ticket["rule_results"]["b06_days_to_expiry"] = days_to_expiry
    ticket["rule_results"]["b06_expiring_soon"] = 0 <= days_to_expiry <= B06_WINDOW_DAYS
    return ticket


# ---------------------------------------------------------------------------
# B-07 Report the leakage
# ---------------------------------------------------------------------------
# Per ticket it records how many worklog hours were delivered outside
# scope. The rule engine's aggregate step sums these by client and by
# function across all tickets.
# ---------------------------------------------------------------------------

def rule_b_07_report_leakage(ticket):
    """
    Compute leakage hours for this ticket.

    Leakage is the total worklog time when the ticket is routed to a
    billable path, and zero otherwise.

    Writes to rule_results:
        b07_leakage_hours  (float)
    """
    route = ticket["rule_results"].get("b04_route")

    total_hours = sum(
        (worklog.get("time_spent_seconds") or 0)
        for worklog in ticket.get("worklogs", [])
    ) / 3600

    ticket["rule_results"]["b07_leakage_hours"] = (
        round(total_hours, 2) if route == "billable_path" else 0
    )
    return ticket


RULES = [
    rule_b_02_check_contract_is_live,
    rule_b_03_check_module_coverage,
    rule_b_04_route_out_of_scope,
    rule_b_05_watch_entitlement_balance,
    rule_b_06_track_contract_expiry,
    rule_b_07_report_leakage,
]