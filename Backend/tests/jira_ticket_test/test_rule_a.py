from app.rules.jira_rules.rule_a import (
    rule_a_01_validate_on_arrival,
    rule_a_02_classify_function,
    rule_a_04_derive_severity,
    rule_a_05_apply_context_modifiers,
    rule_a_06_record_disagreement,
    rule_a_07_run_sla_clock,
    rule_a_08_route_and_escalate,
)
from ticket_factory import make_ticket


# ---------------------------------------------------------------------------
# A-01 Validate
# ---------------------------------------------------------------------------

def test_a01_valid_ticket_passes():
    ticket = make_ticket(client_id="CLIENT-A", environment="Production")
    ticket = rule_a_01_validate_on_arrival(ticket)
    assert ticket["rule_results"]["a01_valid"] is True
    assert ticket["rule_results"]["a01_missing_fields"] == []


def test_a01_missing_client_id_is_flagged():
    ticket = make_ticket(client_id=None)
    ticket = rule_a_01_validate_on_arrival(ticket)
    assert ticket["rule_results"]["a01_valid"] is False
    assert "client_id" in ticket["rule_results"]["a01_missing_fields"]


# ---------------------------------------------------------------------------
# A-02 Classify function
# ---------------------------------------------------------------------------

def test_a02_m3_code_wins_over_keywords():
    ticket = make_ticket(m3_program_code="MMS100", description="warehouse issue")
    ticket = rule_a_02_classify_function(ticket)
    assert ticket["function_area"] == "MMS100"
    assert ticket["rule_results"]["a02_confidence"] == 0.95
    assert ticket["rule_results"]["a02_source"] == "m3_program_code"


def test_a02_keyword_match():
    ticket = make_ticket(m3_program_code=None, description="Invoice will not post")
    ticket = rule_a_02_classify_function(ticket)
    assert ticket["function_area"] == "Finance"
    assert ticket["rule_results"]["a02_source"] == "keywords"


def test_a02_no_signal_leaves_function_empty():
    ticket = make_ticket(m3_program_code=None, description="something happened")
    ticket = rule_a_02_classify_function(ticket)
    assert ticket["function_area"] is None


# ---------------------------------------------------------------------------
# A-04 Derive severity
# ---------------------------------------------------------------------------

def test_a04_critical_keywords_produce_critical():
    ticket = make_ticket(description="Production down, data loss, no workaround")
    ticket = rule_a_04_derive_severity(ticket)
    assert ticket["rule_results"]["a04_severity"] == "Critical"


def test_a04_claimed_priority_is_recorded_not_used():
    ticket = make_ticket(priority="Critical", description="minor cosmetic issue")
    ticket = rule_a_04_derive_severity(ticket)
    assert ticket["rule_results"]["a04_claimed_severity"] == "Critical"
    assert ticket["rule_results"]["a04_severity"] != "Critical"


# ---------------------------------------------------------------------------
# A-05 Context modifiers
# ---------------------------------------------------------------------------

def test_a05_non_production_caps_severity():
    ticket = make_ticket(environment="Test", description="Production down, data loss")
    ticket = rule_a_04_derive_severity(ticket)
    ticket = rule_a_05_apply_context_modifiers(ticket)
    assert ticket["rule_results"]["a04_severity"] == "Medium"
    assert ticket["rule_results"]["a05_cap_reason"] == "non_production"


def test_a05_go_live_imminent_prevents_cap():
    ticket = make_ticket(
        environment="Test",
        description="Production down, data loss",
        go_live_imminent=True,
    )
    ticket = rule_a_04_derive_severity(ticket)
    ticket = rule_a_05_apply_context_modifiers(ticket)
    assert ticket["rule_results"]["a04_severity"] == "Critical"


# ---------------------------------------------------------------------------
# A-06 Severity disagreement
# ---------------------------------------------------------------------------

def test_a06_gap_recorded_when_claimed_and_derived_differ_by_two():
    ticket = make_ticket(priority="Low", description="Production down, data loss")
    ticket = rule_a_04_derive_severity(ticket)
    ticket = rule_a_06_record_disagreement(ticket)
    assert ticket["rule_results"]["a06_severity_disagreement"] is True
    assert ticket["rule_results"]["a06_severity_gap"] == 3


# ---------------------------------------------------------------------------
# A-07 SLA clock
# ---------------------------------------------------------------------------

def test_a07_enterprise_gets_four_hour_sla():
    ticket = make_ticket(customer_tier="Enterprise")
    ticket = rule_a_07_run_sla_clock(ticket)
    assert ticket["rule_results"]["a07_sla_hours"] == 4


def test_a07_standard_gets_twenty_four_hour_sla():
    ticket = make_ticket(customer_tier="Standard")
    ticket = rule_a_07_run_sla_clock(ticket)
    assert ticket["rule_results"]["a07_sla_hours"] == 24


# ---------------------------------------------------------------------------
# A-08 Route and escalate
# ---------------------------------------------------------------------------

def test_a08_critical_pages_duty_manager():
    ticket = make_ticket(function_area="Finance", description="Production down, data loss")
    ticket = rule_a_04_derive_severity(ticket)
    ticket = rule_a_08_route_and_escalate(ticket)
    assert ticket["rule_results"]["a08_page_on_call"] is True
    assert ticket["rule_results"]["a08_escalation_level"] == "IMMEDIATE"


def test_a08_unclassified_function_routes_to_general_support():
    ticket = make_ticket(function_area=None)
    ticket = rule_a_04_derive_severity(ticket)
    ticket = rule_a_08_route_and_escalate(ticket)
    assert ticket["rule_results"]["a08_skill_pool"] == "general_support"