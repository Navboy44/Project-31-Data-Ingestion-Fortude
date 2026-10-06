"""
MongoDB connection and index bootstrap.

This module owns the Mongo client lifecycle and the index definitions.
It does not know anything about Jira, SharePoint, or any other specific
source. All source-specific behaviour comes from the registry in
`source_registration_table.py`.

Responsibilities
----------------
- Create and reuse one AsyncIOMotorClient for the process.
- Expose `get_db()` so other modules can obtain the database handle.
- Create indexes for the shared event collection and for every source
  collection declared in the registry.
- Close the client cleanly on shutdown.

Lifecycle
---------
Call `init_mongo()` once at application startup and `close_mongo()` once
at shutdown. Both are designed to be called from FastAPI's lifespan.

Do not call `init_mongo()` from request handlers. It creates indexes and
is not meant to run repeatedly.
"""

import os

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.outputs.MongoDB.source_registration_table import SOURCES


# Connection settings. Override with environment variables in deployment.
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "Test")

# Module-level singletons. Motor clients are thread-safe and cheap to
# reuse, so the process keeps exactly one client for its lifetime.
_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_client() -> AsyncIOMotorClient:
    """
    Return the shared Mongo client, creating it on first call.

    Motor's AsyncIOMotorClient is lazy: constructing it does not open a
    connection. The first actual operation does. That is why this
    function is safe to call without awaiting anything.
    """
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """
    Return the shared database handle, creating it on first call.

    Every writer and reader in the pipeline calls this instead of
    holding a reference to the database. That keeps the client and
    database singletons in one place.
    """
    global _db
    if _db is None:
        _db = get_client()[MONGO_DB_NAME]
    return _db


async def init_mongo():
    """
    Create every index the pipeline relies on.

    Two groups of indexes are created:

    1. Shared event collection (`document_events`).
       Every source writes its events here, so the indexes must support
       per-source and per-document queries:
           event_id (unique)                - idempotency key
           source                           - filter by source
           document_id                      - filter by ticket/document
           (document_id, occurred_at)       - timeline queries

    2. Per-source collections declared in `SOURCES`.
       For each source:
           - the identity field gets a unique index so upserts cannot
             create duplicates
           - every field listed in spec.indexes gets a standard index

    Adding a new source to the registry automatically creates its
    collection and indexes on the next startup. No changes are needed
    in this file.
    """
    db = get_db()

    # --- Shared event collection -----------------------------------------
    await db.document_events.create_index("event_id", unique=True)
    await db.document_events.create_index("source")
    await db.document_events.create_index("document_id")
    await db.document_events.create_index([("document_id", 1), ("occurred_at", 1)])

    # --- Per-source collections ------------------------------------------
    for spec in SOURCES.values():
        col = db[spec.collection]

        # Identity field is unique. Only string identities are supported
        # by the write path today, so skip callables here.
        if isinstance(spec.identity, str):
            await col.create_index(spec.identity, unique=True)

        for field in spec.indexes:
            await col.create_index(field)

    print("[mongo] indexes ensured")


async def close_mongo():
    """
    Close the shared Mongo client and clear the singletons.

    Called from application shutdown. After this runs, the next call to
    `get_client()` or `get_db()` would create a new client, which is
    why shutdown code should not make further Mongo calls.
    """
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None