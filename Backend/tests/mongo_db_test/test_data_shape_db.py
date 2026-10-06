# tests/mongo/test_data_shape.py

import pytest

from app.outputs.MongoDB.mongo_db_common_func import persist
from app.outputs.MongoDB.mongo_db_output import get_db


@pytest.mark.asyncio
async def test_document_has_source_and_ingested_at(fake_ticket):
    db = get_db()
    await persist("jira", [fake_ticket()])

    doc = await db.jira_tickets.find_one({"ticket_key": "PYTEST-1"})
    assert doc["_source"] == "jira"
    assert "_ingested_at" in doc


@pytest.mark.asyncio
async def test_events_have_required_fields(fake_ticket):
    db = get_db()
    await persist("jira", [fake_ticket()])

    async for row in db.document_events.find({"document_id": "PYTEST-1"}):
        assert "event_id" in row
        assert "source" in row
        assert row["source"] == "jira"
        assert "document_id" in row
        assert "event_type" in row
        assert "occurred_at" in row
        assert "payload" in row


@pytest.mark.asyncio
async def test_event_id_format(fake_ticket):
    db = get_db()
    await persist("jira", [fake_ticket()])

    async for row in db.document_events.find({"document_id": "PYTEST-1"}):
        parts = row["event_id"].split(":")
        assert parts[0] == "jira"
        assert parts[1] == "PYTEST-1"
        assert parts[2] in {"status_change", "comment", "worklog", "attachment", "approval"}