from app.rules.jira_rules.rule_d import (
    rule_d_01_build_history,
    rule_d_02_separate_waiting_from_working,
    rule_d_03_count_reopens,
    rule_d_05_watch_who_is_raising,
)
from ticket_factory import make_ticket, make_status_change


def test_d02_waiting_and_working_separated():
    history = [
        make_status_change("1", "Open", "In Progress", "2026-09-01T10:00:00+0000", duration_seconds=600),
        make_status_change("2", "In Progress", "Waiting for Customer", "2026-09-01T11:00:00+0000", duration_seconds=1800),
        make_status_change("3", "Waiting for Customer", "In Progress", "2026-09-01T12:00:00+0000", duration_seconds=1200),
    ]
    ticket = make_ticket(status_history=history)
    ticket = rule_d_02_separate_waiting_from_working(ticket)
    assert ticket["rule_results"]["d02_working_seconds"] == 1800
    assert ticket["rule_results"]["d02_waiting_seconds"] == 1200


def test_d03_counts_reopens():
    history = [
        make_status_change("1", "Open", "Resolved", "2026-09-01T10:00:00+0000", is_reopen=False),
        make_status_change("2", "Resolved", "In Progress", "2026-09-01T11:00:00+0000", is_reopen=True),
    ]
    ticket = make_ticket(status_history=history)
    ticket = rule_d_03_count_reopens(ticket)
    assert ticket["rule_results"]["d03_reopen_count"] == 1
    assert ticket["rule_results"]["d03_has_reopen"] is True


def test_d05_senior_raiser_detected():
    ticket = make_ticket(reporter_role="Manager")
    ticket = rule_d_05_watch_who_is_raising(ticket)
    assert ticket["rule_results"]["d05_senior_raiser"] is True