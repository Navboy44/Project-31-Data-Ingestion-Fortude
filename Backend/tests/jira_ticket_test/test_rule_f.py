from app.rules.jira_rules.rule_f import (
    rule_f_01_classify_effort,
    rule_f_02_score_confidence,
    rule_f_03_apply_cost_rate,
    rule_f_05_isolate_rework,
    rule_f_07_report_margin,
)
from ticket_factory import make_ticket, make_worklog, make_contract


def test_f01_classifies_billable_project():
    worklogs = [make_worklog("1", 3600, "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(worklogs=worklogs, parent_project="ACME-Implementation")
    ticket = rule_f_01_classify_effort(ticket)
    assert ticket["worklogs"][0]["category"] == "Billable Project"


def test_f01_classifies_out_of_scope():
    worklogs = [make_worklog("1", 3600, "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(worklogs=worklogs, parent_project=None)
    ticket["rule_results"]["b02_contract_live"] = True
    ticket["rule_results"]["b03_in_scope"] = False
    ticket = rule_f_01_classify_effort(ticket)
    assert ticket["worklogs"][0]["category"] == "Out of Scope"


def test_f03_applies_rate():
    worklogs = [make_worklog("1", 3600, "2026-09-01T10:00:00+0000", author_role="Consultant")]
    ticket = make_ticket(worklogs=worklogs, rate_table={"Consultant": 80})
    ticket = rule_f_03_apply_cost_rate(ticket)
    assert ticket["worklogs"][0]["cost"] == 80.0


def test_f07_sums_total_cost():
    worklogs = [
        make_worklog("1", 3600, "2026-09-01T10:00:00+0000"),
        make_worklog("2", 1800, "2026-09-01T11:00:00+0000"),
    ]
    ticket = make_ticket(worklogs=worklogs, rate_table={"Consultant": 80})
    ticket = rule_f_03_apply_cost_rate(ticket)
    ticket = rule_f_07_report_margin(ticket)
    assert ticket["rule_results"]["f07_total_cost"] == 120.0