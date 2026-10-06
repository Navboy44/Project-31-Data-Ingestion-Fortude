# app/db/mongo_common.py

"""
Generic Mongo write path for every registered source.

Reads SOURCES from the source registration table and applies a uniform upsert +
event-append pattern regardless of which connector produced the data.

---------------
upsert_documents
    - One document per identity value.
    - Scalar fields: incoming wins.
    - Nested arrays declared in spec.merge_arrays are merged by event ID
      so re-ingesting the same document never duplicates history.
    - Sub-document blocks (derived, rule_results, metadata) are merged
      per key so rule output and audit trails survive re-ingestion.

append_events
    - One row per item in each array declared in spec.events.
    - Rows are inserted with $setOnInsert keyed by event_id, so replaying
      the same batch is a no-op.

persist
    - One call to run both steps for a source.

Concurrency
-----------
upsert_documents uses find_one + replace_one, which is a read-modify-write
pattern. It is safe for a single pipeline. Two concurrent writers on the
same document can race. Serialize per source if you need concurrency.
"""

from datetime import datetime, timezone
from typing import Iterable

from pymongo import UpdateOne

from app.outputs.MongoDB.mongo_db_output import get_db
from app.outputs.MongoDB.source_registration_table import SOURCES, SourceSpec, _identity


# Sub-document blocks that must be merged per key rather than replaced.
# rule_results is the rule engine output block; metadata is reserved for
# future source enrichment.
_MERGED_SUBDOCUMENTS = ("rule_results", "metadata")

from zoneinfo import ZoneInfo
def _now():
    """Return the current zone time."""
    return datetime.now(ZoneInfo("Australia/Melbourne"))

# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def _merge_by_key(
    existing: list | None,
    incoming: list | None,
    key_field: str,
) -> list:
    """
    Merge two lists of dicts by a stable key.

    Incoming items overwrite existing items with the same key. Items
    without the key are dropped. Order is not preserved; the caller
    sorts afterwards if the ArraySpec requests it.
    """
    if not existing and not incoming:
        return []

    merged: dict = {}

    for item in existing or []:
        if not isinstance(item, dict):
            continue
        key = item.get(key_field)
        if key is not None:
            merged[key] = item

    for item in incoming or []:
        if not isinstance(item, dict):
            continue
        key = item.get(key_field)
        if key is not None:
            merged[key] = item

    return list(merged.values())


def _merge_document(existing: dict | None, incoming: dict, spec: SourceSpec) -> dict:
    """
    Merge an incoming canonical document onto the existing Mongo document.

    Scalars: incoming wins.
    Nested arrays: merged by event ID, then sorted if the spec asks.
    Sub-documents (derived, rule_results, metadata): merged per key.
    """
    if not existing:
        merged = dict(incoming)
    else:
        merged = {**existing, **incoming}

        # Nested arrays: merge by key, then sort if requested.
        for array_spec in spec.merge_arrays:
            field = array_spec.field
            merged[field] = _merge_by_key(
                existing.get(field),
                incoming.get(field),
                array_spec.key,
            )
            if array_spec.sort:
                merged[field].sort(
                    key=lambda item: (
                        item.get(array_spec.sort) or ""
                    ) if isinstance(item, dict) else ""
                )

        # Sub-documents: merge per key so rule output and audit trails
        # survive re-ingestion. A shallow document-level merge would
        # replace them entirely.
        for block in _MERGED_SUBDOCUMENTS:
            if block in existing or block in incoming:
                merged[block] = {
                    **(existing.get(block) or {}),
                    **(incoming.get(block) or {}),
                }

    merged["_ingested_at"] = _now()
    merged["_source"] = spec.source
    return merged


# ---------------------------------------------------------------------------
# Generic upsert
# ---------------------------------------------------------------------------

async def upsert_documents(source: str, docs: Iterable[dict]) -> dict:
    """
    Upsert a batch of canonical documents for one source.

    Uses SOURCES[source] to decide the target collection, the identity
    field, and the nested arrays to merge.

    Returns a summary with counts of inserted, modified, matched, and
    skipped documents.
    """
    spec = SOURCES.get(source)
    if spec is None:
        raise ValueError(f"Unknown source: {source}")

    if callable(spec.identity):
        raise NotImplementedError(
            "Callable identity is not supported by the write path yet. "
            "Use a string field name in SourceSpec.identity."
        )

    col = get_db()[spec.collection]

    inserted = modified = matched = skipped = 0

    for doc in docs:
        key = _identity(doc, spec)
        if not key:
            skipped += 1
            continue

        existing = await col.find_one({spec.identity: key})
        merged = _merge_document(existing, doc, spec)

        result = await col.replace_one({spec.identity: key}, merged, upsert=True)

        if result.upserted_id is not None:
            inserted += 1
        elif result.modified_count > 0:
            modified += 1
        else:
            matched += 1

    return {
        "source": source,
        "inserted": inserted,
        "modified": modified,
        "matched": matched,
        "skipped": skipped,
    }


# ---------------------------------------------------------------------------
# Generic event append
# ---------------------------------------------------------------------------

def _build_event_rows(doc: dict, spec: SourceSpec) -> list[dict]:
    """
    Flatten the arrays declared in spec.events into event rows.

    Each row carries a stable event_id so the same event can be written
    repeatedly without creating duplicates.
    """
    key = _identity(doc, spec)
    if not key:
        return []

    rows = []

    for event_spec in spec.events:
        for item in doc.get(event_spec.array_field) or []:
            if not isinstance(item, dict):
                continue

            item_id = item.get(event_spec.id_field)
            if item_id is None:
                continue

            rows.append({
                "event_id": f"{spec.source}:{key}:{event_spec.event_type}:{item_id}",
                "source": spec.source,
                "document_id": key,
                "event_type": event_spec.event_type,
                "occurred_at": item.get(event_spec.occurred_at),
                "payload": item,
            })

    return rows


async def append_events(source: str, docs: Iterable[dict]) -> int:
    """
    Write event rows for every nested array item in the batch.

    Uses $setOnInsert keyed by event_id, so replaying the same batch is
    a no-op. Returns the number of newly inserted events.
    """
    spec = SOURCES.get(source)
    if spec is None:
        raise ValueError(f"Unknown source: {source}")

    col = get_db()[spec.events_collection]

    rows = []
    for doc in docs:
        rows.extend(_build_event_rows(doc, spec))

    if not rows:
        return 0

    ops = [
        UpdateOne({"event_id": row["event_id"]}, {"$setOnInsert": row}, upsert=True)
        for row in rows
    ]

    result = await col.bulk_write(ops, ordered=False)

    # $setOnInsert never modifies an existing document, so the meaningful
    # number is the count of newly inserted events. Matched-but-unchanged
    # operations are replay and are intentionally not counted.
    return result.upserted_count or 0


# ---------------------------------------------------------------------------
# Convenience: one call for the whole write path
# ---------------------------------------------------------------------------

async def persist(source: str, docs: Iterable[dict]) -> dict:
    """
    Upsert documents and append their events in one call.

    This is the entry point the pipeline should use. Both steps are
    idempotent, so calling persist twice with the same batch produces
    the same Mongo state.
    """
    upsert_summary = await upsert_documents(source, docs)
    event_count = await append_events(source, docs)
    return {
        **upsert_summary,
        "events_appended": event_count,
    }