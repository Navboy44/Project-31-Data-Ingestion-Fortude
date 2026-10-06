# tests/mongo/test_persist_idempotency.py

import pytest

from app.outputs.MongoDB.mongo_db_common_func import persist
from app.outputs.MongoDB.mongo_db_output import get_db


@pytest.mark.asyncio
async def test_second_persist_does_not_insert_document(fake_ticket):
    ticket = fake_ticket()

    first = await persist("jira", [ticket])
    second = await persist("jira", [ticket])

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    # The document is re-stamped with _ingested_at, so Mongo reports it
    # as modified. The important guarantee is that nothing was inserted.
    assert second["modified"] == 1
    assert second["matched"] == 0


@pytest.mark.asyncio
async def test_second_persist_does_not_duplicate_events(fake_ticket):
    db = get_db()
    ticket = fake_ticket()

    await persist("jira", [ticket])
    after_first = await db.document_events.count_documents({"document_id": "PYTEST-1"})

    await persist("jira", [ticket])
    after_second = await db.document_events.count_documents({"document_id": "PYTEST-1"})

    assert after_first == after_second


@pytest.mark.asyncio
async def test_second_persist_does_not_duplicate_nested_arrays(fake_ticket):
    db = get_db()
    ticket = fake_ticket()

    await persist("jira", [ticket])
    first_doc = await db.jira_tickets.find_one({"ticket_key": "PYTEST-1"})

    await persist("jira", [ticket])
    second_doc = await db.jira_tickets.find_one({"ticket_key": "PYTEST-1"})

    assert len(first_doc["comments"]) == len(second_doc["comments"])
    assert len(first_doc["status_history"]) == len(second_doc["status_history"])
    assert len(first_doc["worklogs"]) == len(second_doc["worklogs"])


@pytest.mark.asyncio
async def test_merge_adds_new_comment_without_losing_old(fake_ticket):
    db = get_db()
    ticket = fake_ticket()
    await persist("jira", [ticket])

    # Same ticket, one more comment
    ticket2 = fake_ticket()
    ticket2["comments"].append({
        "comment_id": "c2",
        "author": "Alice",
        "body": "Second comment",
        "body_clean": "Second comment",
        "created": "2026-09-23T11:00:00+0000",
        "updated": "2026-09-23T11:00:00+0000",
        "is_internal": False,
    })

    await persist("jira", [ticket2])

    doc = await db.jira_tickets.find_one({"ticket_key": "PYTEST-1"})
    comment_ids = {c["comment_id"] for c in doc["comments"]}

    assert comment_ids == {"c1", "c2"}
    assert len(doc["comments"]) == 2


@pytest.mark.asyncio
async def test_merge_updates_existing_comment(fake_ticket):
    db = get_db()
    ticket = fake_ticket()
    await persist("jira", [ticket])

    # Same comment_id, new body
    ticket2 = fake_ticket()
    ticket2["comments"][0]["body_clean"] = "Edited body"

    await persist("jira", [ticket2])

    doc = await db.jira_tickets.find_one({"ticket_key": "PYTEST-1"})
    assert len(doc["comments"]) == 1
    assert doc["comments"][0]["body_clean"] == "Edited body"