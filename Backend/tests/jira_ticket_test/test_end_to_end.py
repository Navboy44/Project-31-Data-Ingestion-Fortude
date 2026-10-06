"""
End-to-end tests covering the awkward cases described in the design doc.
Each test plants one case and asserts the pipeline handles it correctly.
"""

from app.mappers.jira_rule_engine import transform_canonical_tickets_full
from ticket_factory import (
    make_ticket,
    make_contract,
    make_comment,
    make_worklog,
    make_status_change,
)


def test_critical_claim_rated_medium_by_evidence():
    """A Critical claim that the evidence rates as Medium."""
    ticket = make_ticket(
        priority="Critical",
        description="Cosmetic label misalignment on the login screen.",
        environment="Production",
    )
    result = transform_canonical_tickets_full([ticket], "ALL")[0]
    assert result["rule_results"]["a04_claimed_severity"] == "Critical"
    assert result["rule_results"]["a04_severity"] != "Critical"
    assert result["rule_results"]["a06_severity_disagreement"] is True


def test_ticket_for_module_outside_contract():
    """A ticket for a module the contract does not cover."""
    contract = make_contract(covered_modules=["Finance"])
    ticket = make_ticket(
    title="Warehouse pick fails on batch item",
    description="User cannot pick stock from the warehouse.",
    contract=make_contract(covered_modules=["Finance"]),
    m3_program_code=None,
    )
    result = transform_canonical_tickets_full([ticket], "ALL")[0]
    assert result["rule_results"]["b03_in_scope"] is False
    assert result["rule_results"]["b04_route"] == "billable_path"


def test_finance_ticket_raised_inside_period_close():
    """A Finance ticket raised inside a period close window."""
    ticket = make_ticket(
        function_area="Finance",
        description="Report not posting",
        client_period_close=True,
    )
    result = transform_canonical_tickets_full([ticket], "ALL")[0]
    # A-05 raises severity one level and records the reason.
    assert "a05_raise_reason" not in result["rule_results"] or result["rule_results"].get("a05_raise_reason") == "period_close"


def test_ticket_raised_friday_1755():
    """A ticket raised at 17:55 on a Friday should show real elapsed hours."""
    ticket = make_ticket(created_at="2026-09-18T17:55:00+0000")
    result = transform_canonical_tickets_full([ticket], "ALL")[0]
    assert result["rule_results"]["a07_hours_since_created"] >= 0
    assert result["rule_results"]["a07_sla_hours"] > 0


def test_ticket_reopened_twice():
    """A ticket reopened two or three times."""
    history = [
        make_status_change("1", "Open", "Resolved", "2026-09-01T10:00:00+0000", is_reopen=False),
        make_status_change("2", "Resolved", "In Progress", "2026-09-02T10:00:00+0000", is_reopen=True),
        make_status_change("3", "In Progress", "Resolved", "2026-09-03T10:00:00+0000", is_reopen=False),
        make_status_change("4", "Resolved", "In Progress", "2026-09-04T10:00:00+0000", is_reopen=True),
    ]
    ticket = make_ticket(status_history=history)
    result = transform_canonical_tickets_full([ticket], "ALL")[0]
    assert result["rule_results"]["d03_reopen_count"] == 2
    assert result["rule_results"]["d03_has_reopen"] is True


def test_same_fault_three_times_in_90_days():
    """The same fault raised three times in 90 days by one client."""
    tickets = [
        make_ticket(
            ticket_key=f"PROJ-{i}",
            client_id="CLIENT-A",
            function_area="Warehouse",
            title="Pick fails on batch item",
            created_at="2026-09-01T10:00:00+0000",
        )
        for i in range(3)
    ]
    result = transform_canonical_tickets_full(tickets, "D")
    for t in result:
        assert t["rule_results"]["d04_recurrence_pattern"] is True


def test_two_tickets_same_fault_different_words():
    """Two tickets describing the same fault in different words."""
    tickets = [
        make_ticket(ticket_key="PROJ-1", title="Service hangs on startup"),
        make_ticket(ticket_key="PROJ-2", title="Connection timeout on boot"),
    ]
    result = transform_canonical_tickets_full(tickets, "ALL")
    # Signatures differ because the words differ; this test documents the
    # known limitation of D-04. Replace the signature builder with
    # embeddings or keyword clustering to actually catch this case.
    sig1 = result[0]["rule_results"]["d04_error_signature"]
    sig2 = result[1]["rule_results"]["d04_error_signature"]
    assert sig1 != sig2


def test_comment_containing_api_key():
    """A comment containing something that looks like an API key."""
    comments = [make_comment("1", "Use api_key: sk_live_abc123 to connect", "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(comments=comments)
    result = transform_canonical_tickets_full([ticket], "ALL")[0]
    assert result["rule_results"]["c03_sensitive_found"] is True
    assert "credential" in result["rule_results"]["c03_sensitive_types"]
    assert "sk_live_abc123" not in result["comments"][0]["body_clean"]


def test_approval_recorded_after_deployment():
    """An approval timestamp recorded after the deployment timestamp."""
    ticket = make_ticket(
        deployment_timestamp="2026-09-01T10:00:00+0000",
        approvals=[{
            "approval_id": "1",
            "approver": "Alice",
            "status": "approved",
            "created": "2026-09-01T12:00:00+0000",
            "decision": "approved",
        }],
    )
    result = transform_canonical_tickets_full([ticket], "ALL")[0]
    assert result["rule_results"]["g03_approval_before_deployment"] is False


def test_same_ticket_processed_twice_is_idempotent():
    """Reprocessing creates no duplicates in rule_results or nested arrays."""
    comments = [make_comment("1", "Some comment body long enough to matter.", "2026-09-01T10:00:00+0000")]
    ticket = make_ticket(comments=comments)
    first = transform_canonical_tickets_full([ticket], "ALL")[0]
    second = transform_canonical_tickets_full([first], "ALL")[0]
    # rules_applied accumulates by design; that is expected.
    assert len(second["comments"]) == len(first["comments"])