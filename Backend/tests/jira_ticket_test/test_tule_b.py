from app.rules.jira_rules.rule_b import (
    rule_b_02_check_contract_is_live,
    rule_b_03_check_module_coverage,
    rule_b_04_route_out_of_scope,
    rule_b_05_watch_entitlement_balance,
    rule_b_07_report_leakage,
)
from ticket_factory import make_ticket, make_contract, make_worklog


def test_b02_no_contract_not_live():
    ticket = make_ticket(contract=None)
    ticket = rule_b_02_check_contract_is_live(ticket)
    assert ticket["rule_results"]["b02_contract_live"] is False


def test_b03_coverage_true_when_function_in_modules():
    contract = make_contract(covered_modules=["Warehouse", "Order"])
    ticket = make_ticket(function_area="Warehouse", contract=contract)
    ticket["rule_results"]["a02_confidence"] = 0.9
    ticket = rule_b_03_check_module_coverage(ticket)
    assert ticket["rule_results"]["b03_in_scope"] is True


def test_b03_coverage_none_when_a02_low_confidence():
    contract = make_contract(covered_modules=["Warehouse"])
    ticket = make_ticket(function_area="Warehouse", contract=contract)
    ticket["rule_results"]["a02_confidence"] = 0.4
    ticket = rule_b_03_check_module_coverage(ticket)
    assert ticket["rule_results"]["b03_in_scope"] is None


def test_b04_out_of_scope_routes_to_billable_path():
    ticket = make_ticket()
    ticket["rule_results"]["b02_contract_live"] = True
    ticket["rule_results"]["b03_in_scope"] = False
    ticket = rule_b_04_route_out_of_scope(ticket)
    assert ticket["rule_results"]["b04_route"] == "billable_path"
    assert ticket["rule_results"]["b04_requires_estimate"] is True


def test_b05_threshold_breached_at_80_percent():
    contract = make_contract(entitled_hours=100, consumed_hours=85)
    ticket = make_ticket(contract=contract)
    ticket = rule_b_05_watch_entitlement_balance(ticket)
    assert ticket["rule_results"]["b05_threshold_breached"] is True


def test_b07_leakage_only_on_billable_path():
    worklogs = [make_worklog("1", 3600, "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(worklogs=worklogs)
    ticket["rule_results"]["b04_route"] = "billable_path"
    ticket = rule_b_07_report_leakage(ticket)
    assert ticket["rule_results"]["b07_leakage_hours"] == 1.0

    ticket2 = make_ticket(worklogs=worklogs)
    ticket2["rule_results"]["b04_route"] = "support_queue"
    ticket2 = rule_b_07_report_leakage(ticket2)
    assert ticket2["rule_results"]["b07_leakage_hours"] == 0