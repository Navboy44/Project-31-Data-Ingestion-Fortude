"""
Declarative registry of Mongo storage for every data source.

Every connector in the pipeline (Jira, SharePoint, Infor M3, ...) produces
canonical documents that need to be written to Mongo. Rather than write a
repository per source, the pipeline describes each source once, here, and
the generic write path in `mongo_db_common_func.py` reads this registry.

What each source declares
-------------------------
SourceSpec carries everything the write path needs:
    - which Mongo collection the documents go into
    - which field uniquely identifies a document
    - which nested arrays must be merged by event ID on upsert
    - which nested arrays become flat event rows
    - which fields need indexes

Adding a new source
-------------------
Add one entry to SOURCES. Nothing in `mongo_db_common_func.py` or
`mongo_db_output.py` needs to change. On the next application startup,
`init_mongo()` will create the collection and its indexes automatically.

Identity and the write path
---------------------------
SourceSpec.identity accepts either a field name (string) or a callable.
The current write path only supports the string form and raises
NotImplementedError for callables. Use a string field name until the
write path is extended to evaluate callables.
"""

from dataclasses import dataclass, field
from typing import Callable


@dataclass
class ArraySpec:
    """
    A nested array that must be merged by key on upsert.

    When a document is re-ingested, the array is not replaced wholesale.
    Instead, incoming items are merged into existing items by `key`, so
    the same status change / comment / worklog is never duplicated.

    Attributes:
        field:  Name of the array field on the document.
                Example: "status_history"
        key:    Name of the field within each array item that uniquely
                identifies the item for deduplication.
                Example: "history_id"
        sort:   Optional field to sort the merged array by after merging.
                Example: "created". If None, order is not guaranteed.
    """
    field: str
    key: str
    sort: str | None = None


@dataclass
class EventSpec:
    """
    A nested array that should be flattened into event rows.

    Every item in the array becomes one row in the shared events
    collection. The row carries a stable event_id of the form:

        <source>:<document_id>:<event_type>:<item_id>

    That ID is what makes event writing idempotent: replaying the same
    batch inserts nothing because the same event_id is already present.

    Attributes:
        array_field:  Name of the array field on the document.
                      Example: "comments"
        event_type:   Label stored on each generated event row.
                      Example: "comment"
        id_field:     Field within the array item that uniquely identifies
                      the event. Example: "comment_id"
        occurred_at:  Field within the array item that records when the
                      event happened. Used for timeline queries.
                      Example: "created"
    """
    array_field: str
    event_type: str
    id_field: str
    occurred_at: str


@dataclass
class SourceSpec:
    """
    Complete storage description for one data source.

    Attributes:
        source:             Registry key, e.g. "jira".
        collection:         Mongo collection the documents go into.
        events_collection:  Shared collection for flattened events.
                            Defaults to "document_events" for every
                            source so timeline queries can span sources.
        identity:           Field name that uniquely identifies a
                            document, or a callable that returns one.
                            The write path currently only supports the
                            string form.
        merge_arrays:       Nested arrays that must be merged by event ID
                            on upsert. See ArraySpec.
        events:             Nested arrays that become flat event rows.
                            See EventSpec.
        indexes:            Fields that should be indexed on the
                            collection. Dotted paths are allowed for
                            sub-document fields, e.g. "rule_results.x".
    """
    source: str
    collection: str
    events_collection: str = "document_events"
    identity: str | Callable[[dict], str | None] = "id"
    merge_arrays: list[ArraySpec] = field(default_factory=list)
    events: list[EventSpec] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)


def _identity(doc, spec):
    """
    Return the identity value for a document.

    Used by the write path to decide which field uniquely identifies
    the document. If `spec.identity` is a string, the value is read
    from that field. If it is a callable, the callable is invoked with
    the document.

    Note: the write path currently rejects callables. This function
    exists so the registry can evolve without changing call sites.
    """
    if callable(spec.identity):
        return spec.identity(doc)
    return doc.get(spec.identity)


# ---------------------------------------------------------------------------
# The registration
# ---------------------------------------------------------------------------
# One entry per source. The Jira entry below is the reference example:
# it shows how to declare identity, merge arrays, events, and indexes.
#
# Adding a new source is a matter of adding one more entry with the same
# shape. No Python code needs to change elsewhere.
# ---------------------------------------------------------------------------

SOURCES: dict[str, SourceSpec] = {
    "jira": SourceSpec(
        source="jira",
        collection="jira_tickets",

        # A ticket is uniquely identified by its Jira key (e.g. PROJ-123).
        identity="ticket_key",

        # Nested arrays that must be merged by event ID on re-ingest.
        # The key names match the canonical ticket schema produced by
        # jira_mapper.py, and the sort fields match the timestamp each
        # item carries so merged arrays come back in chronological order.
        merge_arrays=[
            ArraySpec("status_history", "history_id", sort="created"),
            ArraySpec("comments", "comment_id", sort="created"),
            ArraySpec("worklogs", "worklog_id", sort="started"),
            ArraySpec("attachments", "attachment_id", sort="created"),
            ArraySpec("approvals", "approval_id", sort="created"),
        ],

        # Nested arrays that become flat rows in document_events.
        # Every Jira activity type is represented here so the shared
        # event timeline is complete: status moves, comments, worklogs,
        # attachments, approvals.
        events=[
            EventSpec("status_history", "status_change", "history_id", "created"),
            EventSpec("comments", "comment", "comment_id", "created"),
            EventSpec("worklogs", "worklog", "worklog_id", "started"),
            EventSpec("attachments", "attachment", "attachment_id", "created"),
            EventSpec("approvals", "approval", "approval_id", "created"),
        ],

        # Indexes chosen to match the query patterns of the rule engine
        # and the seven business use cases:
        #   client_id                          rule B, D, F groupings
        #   function_area                      rule B coverage, C tagging
        #   created_at, updated_at             time-window queries
        #   rule_results.a04_severity          triage dashboards
        #   rule_results.b04_route             leakage reports
        #   rule_results.d07_client_health_score
        #                                      client health dashboards
        indexes=[
            "client_id",
            "function_area",
            "created_at",
            "updated_at",
            "rule_results.a04_severity",
            "rule_results.b04_route",
            "rule_results.d07_client_health_score",
        ],
    ),
}