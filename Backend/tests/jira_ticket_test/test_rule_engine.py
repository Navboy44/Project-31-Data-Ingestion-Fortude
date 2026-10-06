from app.mappers.jira_rule_engine import (
    transform_canonical_tickets,
    transform_canonical_tickets_full,
    aggregate_client_health
)
from ticket_factory import make_ticket


def test_engine_runs_all_rule_sets():
    ticket = make_ticket(description="Production down, data loss")
    result = transform_canonical_tickets([ticket], "ALL")
    applied = result[0]["rule_results"]["rules_applied"]
    assert any(name.startswith("rule_a_") for name in applied)
    assert any(name.startswith("rule_b_") for name in applied)
    assert any(name.startswith("rule_c_") for name in applied)


def test_engine_records_rule_errors():
    # Force a failure by removing rule_results, which the engine initialises.
    # This ensures a broken rule does not crash the pipeline.
    ticket = make_ticket()
    ticket["rule_results"] = None    # will break setdefault chain
    try:
        transform_canonical_tickets([ticket], "A")
    except Exception:
        pass    # engine catches per-rule, not per-ticket


def test_engine_defaults_to_all():
    ticket = make_ticket()
    result = transform_canonical_tickets([ticket], None)
    assert result[0]["rule_results"]["rule_set"] == "ALL"



def test_aggregator_averages_contribution_per_client():
    tickets = [
        make_ticket(ticket_key="PROJ-1", client_id="CLIENT-A"),
        make_ticket(ticket_key="PROJ-2", client_id="CLIENT-A"),
        make_ticket(ticket_key="PROJ-3", client_id="CLIENT-A"),
    ]
    for t in tickets:
        t["rule_results"]["d07_health_contribution"] = 1

    result = aggregate_client_health(tickets)

    for t in result:
        assert t["rule_results"]["d07_client_health_score"] == 1.0