
import pytest

from app.outputs.MongoDB.mongo_db_output import get_db, init_mongo
from app.outputs.MongoDB.source_registration_table import SOURCES


@pytest.mark.asyncio
async def test_mongo_ping_succeeds():
    db = get_db()
    result = await db.command("ping")
    assert result.get("ok") == 1.0


@pytest.mark.asyncio
async def test_jira_collection_exists():
    await init_mongo()
    db = get_db()
    collections = await db.list_collection_names()
    assert SOURCES["jira"].collection in collections


@pytest.mark.asyncio
async def test_event_collection_exists():
    await init_mongo()
    db = get_db()
    collections = await db.list_collection_names()
    assert "document_events" in collections


@pytest.mark.asyncio
async def test_jira_identity_index_is_unique():
    await init_mongo()
    db = get_db()
    indexes = await db.jira_tickets.index_information()

    # Find the index on ticket_key
    found = None
    for name, info in indexes.items():
        if info.get("key") == [("ticket_key", 1)]:
            found = info
            break

    assert found is not None, "No index on ticket_key"
    assert found.get("unique") is True


@pytest.mark.asyncio
async def test_every_registry_index_exists():
    await init_mongo()
    db = get_db()

    for spec in SOURCES.values():
        col = db[spec.collection]
        indexes = await col.index_information()
        indexed_fields = {tuple(info["key"][0] for _ in [0]) for info in indexes.values()}

        for field in spec.indexes:
            # Flatten dotted paths into the same tuple form Mongo uses
            key_tuple = tuple([(field, 1)])
            assert any(
                info["key"] == [(field, 1)]
                for info in indexes.values()
            ), f"Missing index on {spec.collection}.{field}"


@pytest.mark.asyncio
async def test_event_id_index_is_unique():
    await init_mongo()
    db = get_db()
    indexes = await db.document_events.index_information()

    found = None
    for info in indexes.values():
        if info.get("key") == [("event_id", 1)]:
            found = info
            break

    assert found is not None
    assert found.get("unique") is True