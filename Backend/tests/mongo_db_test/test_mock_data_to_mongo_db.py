# tests/mongo/test_persist_fake.py

import pytest

from app.outputs.MongoDB.mongo_db_common_func import persist
from app.outputs.MongoDB.mongo_db_output import get_db


@pytest.mark.asyncio
async def test_first_persist_inserts_document(fake_ticket):
    db = get_db()
    summary = await persist("jira", [fake_ticket()])

    assert summary["inserted"] == 1
    assert summary["skipped"] == 0
    assert summary["events_appended"] == 3   # 1 status + 1 comment + 1 worklog

    doc = await db.jira_tickets.find_one({"ticket_key": "PYTEST-1"})
    assert doc is not None
    assert doc["title"] == "Fake ticket for testing"


@pytest.mark.asyncio
async def test_persist_skips_document_without_identity(fake_ticket):
    ticket = fake_ticket()
    ticket["ticket_key"] = None

    summary = await persist("jira", [ticket])

    assert summary["inserted"] == 0
    assert summary["skipped"] == 1


@pytest.mark.asyncio
async def test_persist_writes_events(fake_ticket):
    db = get_db()
    await persist("jira", [fake_ticket()])

    count = await db.document_events.count_documents({"document_id": "PYTEST-1"})
    assert count == 3

    # Check the event types
    types = set()
    async for row in db.document_events.find({"document_id": "PYTEST-1"}):
        types.add(row["event_type"])

    assert types == {"status_change", "comment", "worklog"}


@pytest.mark.asyncio
async def test_persist_stores_nested_arrays(fake_ticket):
    db = get_db()
    await persist("jira", [fake_ticket()])

    doc = await db.jira_tickets.find_one({"ticket_key": "PYTEST-1"})
    assert len(doc["status_history"]) == 1
    assert len(doc["comments"]) == 1
    assert len(doc["worklogs"]) == 1


@pytest.mark.asyncio
async def test_persist_preserves_rule_results(fake_ticket):
    ticket = fake_ticket()
    ticket["rule_results"] = {"a04_severity": "High", "b04_route": "support_queue"}

    db = get_db()
    await persist("jira", [ticket])

    doc = await db.jira_tickets.find_one({"ticket_key": "PYTEST-1"})
    assert doc["rule_results"]["a04_severity"] == "High"
    assert doc["rule_results"]["b04_route"] == "support_queue"


@pytest.mark.asyncio
async def test_persist_raises_for_unknown_source(fake_ticket):
    with pytest.raises(ValueError):
        await persist("not-a-real-source", [fake_ticket()])