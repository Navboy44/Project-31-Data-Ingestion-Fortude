# tests/fixtures/ticket_factory.py

from datetime import datetime, timezone


def make_ticket(
    ticket_key="PROJ-1",
    title="Test ticket",
    description="Default description for the test ticket.",
    issue_type="Bug",
    status="In Progress",
    priority="Medium",
    environment="Production",
    labels=None,
    customer_tier="Standard",
    client_id="CLIENT-A",
    contract_id=None,
    function_area=None,
    m3_program_code=None,
    created_at=None,
    resolution=None,
    status_history=None,
    comments=None,
    worklogs=None,
    approvals=None,
    attachments=None,
    contract=None,
    rate_table=None,
    client_baseline=None,
    closed_periods=None,
    reporter="Jane Doe",
    reporter_role="customer",
    assignee="John Smith",
    **extra,
):
    """
    Build a canonical ticket for testing.

    Every field the mapper would produce has a default. Pass any value
    to override it. Extra keyword arguments are merged at the top level
    so you can add fields the mapper does not yet produce.
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()

    ticket = {
        "source": "jira",
        "ticket_id": "10001",
        "ticket_key": ticket_key,
        "title": title,
        "issue_type": issue_type,
        "description": description,
        "status": status,
        "priority": priority,
        "assignee": assignee,
        "reporter": reporter,
        "reporter_role": reporter_role,
        "created_at": created_at,
        "updated_at": created_at,
        "resolution": resolution,
        "resolution_date": None,
        "labels": labels or [],
        "is_L3": "L3" in (issue_type or ""),
        "customer_tier": customer_tier,
        "assigned_team": "Test Project",
        "project_key": "PROJ",
        "project_name": "Test Project",
        "components": [],
        "environment": environment,
        "client_id": client_id,
        "contract_id": contract_id,
        "m3_program_code": m3_program_code,
        "function_area": function_area,
        "risk_level": None,
        "sensitive_system": None,
        "change_type": None,
        "emergency_change": None,
        "approver_list": None,
        "deployment_timestamp": None,
        "rollback_plan": None,
        "testing_evidence": None,
        "parent_project": None,
        "status_history": status_history or [],
        "comments": comments or [],
        "worklogs": worklogs or [],
        "approvals": approvals or [],
        "attachments": attachments or [],
        "contract": contract,
        "rate_table": rate_table,
        "client_baseline": client_baseline,
        "closed_periods": closed_periods or [],
        "rule_results": {},
    }
    ticket.update(extra)
    return ticket


def make_status_change(history_id, from_status, to_status, created, author="Jane Doe", is_reopen=False, duration_seconds=0):
    return {
        "history_id": history_id,
        "author": author,
        "created": created,
        "from": from_status,
        "to": to_status,
        "duration_in_previous_status_seconds": duration_seconds,
        "is_reopen": is_reopen,
    }


def make_comment(comment_id, body, created, author="Jane Doe", is_internal=False):
    return {
        "comment_id": comment_id,
        "author": author,
        "body": body,
        "body_clean": body,
        "created": created,
        "updated": created,
        "is_internal": is_internal,
    }


def make_worklog(worklog_id, seconds, started, author="John Smith", author_role="Consultant"):
    return {
        "worklog_id": worklog_id,
        "author": author,
        "author_role": author_role,
        "time_spent_seconds": seconds,
        "started": started,
        "comment": "",
    }


def make_contract(
    contract_id="C-001",
    covered_modules=None,
    entitled_hours=100,
    consumed_hours=0,
    start_date="2020-01-01",
    end_date="2099-12-31",
):
    return {
        "contract_id": contract_id,
        "covered_modules": covered_modules or ["Warehouse"],
        "entitled_hours": entitled_hours,
        "consumed_hours": consumed_hours,
        "start_date": start_date,
        "end_date": end_date,
    }