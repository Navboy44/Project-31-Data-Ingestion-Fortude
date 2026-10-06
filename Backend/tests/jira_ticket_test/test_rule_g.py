from app.rules.jira_rules.rule_g import (
    rule_g_01_check_completeness,
    rule_g_02_check_real_approval,
    rule_g_03_check_order_of_events,
    rule_g_04_check_separation_of_duties,
    rule_g_06_catch_mislabelled_change,
)
from ticket_factory import make_ticket


def test_g01_detects_missing_evidence():
    ticket = make_ticket()
    ticket = rule_g_01_check_completeness(ticket)
    assert ticket["rule_results"]["g01_complete"] is False
    assert "rollback_plan" in ticket["rule_results"]["g01_missing"]


def test_g02_no_real_approval():
    ticket = make_ticket(approver_list=["Alice", "Bob"], approvals=[])
    ticket = rule_g_02_check_real_approval(ticket)
    assert ticket["rule_results"]["g02_real_approval"] is False


def test_g03_approval_after_deployment_is_flagged():
    ticket = make_ticket(
        deployment_timestamp="2026-09-01T10:00:00+0000",
        approvals=[{
            "approval_id": "1",
            "approver": "Alice",
            "status": "approved",
            "created": "2026-09-01T11:00:00+0000",
            "decision": "approved",
        }],
    )
    ticket = rule_g_03_check_order_of_events(ticket)
    assert ticket["rule_results"]["g03_approval_before_deployment"] is False


def test_g06_routine_sensitive_change_flagged():
    ticket = make_ticket(change_type="Routine", sensitive_system=True)
    ticket = rule_g_06_catch_mislabelled_change(ticket)
    assert ticket["rule_results"]["g06_mislabelled"] is True