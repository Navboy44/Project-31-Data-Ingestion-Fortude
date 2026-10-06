"""
Canonical mapper for Jira tickets.

This module converts the raw JSON returned by the Jira REST API into the
canonical ticket schema used by the rule engine and downstream writers.

It is the only place that knows the shape of Jira's responses. Every other
module in the pipeline works with the canonical shape defined here.

Canonical ticket sections
-------------------------
- Top-level scalars: ticket identity, status, priority, timestamps.
- Nested arrays:    status_history, comments, worklogs, approvals, attachments.
- Injected data:    contract, rate_table, client_baseline, closed_periods.
- rule_results data:     rule output, written later by the rule engine.
"""

from datetime import datetime


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def get_nested_value(data, keys, default=None):
    """
    Safely read a nested value from a dict.

    Walks `keys` one level at a time. If any intermediate value is not a dict
    or is missing, returns `default` instead of raising.

    Example:
        get_nested_value(fields, ["status", "name"]) -> "In Progress"
    """
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _parse_ts(value):
    """
    Parse a Jira timestamp into a datetime object.

    Jira returns ISO 8601 timestamps with or without microseconds. Both
    formats are attempted. Returns None if the value cannot be parsed.
    """
    if not value:
        return None

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None


def _seconds_between(start_iso, end_iso):
    """
    Return the number of whole seconds between two Jira timestamps.

    Returns 0 if either timestamp is missing or unparseable so callers do
    not need to guard against None values.
    """
    start = _parse_ts(start_iso)
    end = _parse_ts(end_iso)

    if not start or not end:
        return 0
    return int((end - start).total_seconds())


# ---------------------------------------------------------------------------
# Ticket level mapping
# ---------------------------------------------------------------------------

def map_jira_issue_to_canonical(issue):
    """
    Map one Jira issue payload to the canonical ticket schema.

    This produces the top-level scalar fields only. Nested arrays such as
    status_history, comments and worklogs are attached later by
    `map_jira_bundle_to_canonical`.

    Args:
        issue: A single item from the "issues" list returned by Jira search.

    Returns:
        A canonical ticket dict with placeholders for fields that are
        filled in later (injected data, derived rule output).
    """
    fields = issue.get("fields", {})
    labels = fields.get("labels", [])
    issue_type = get_nested_value(fields, ["issuetype", "name"])

    # Customer tier is derived from labels. "enterprise" anywhere in the
    # label list promotes the ticket to the Enterprise SLA track.
    customer_tier = "Standard"
    for label in labels:
        if label.lower() == "enterprise":
            customer_tier = "Enterprise"

    reporter = get_nested_value(fields, ["reporter", "displayName"])
    reporter_role = get_nested_value(fields, ["reporter", "accountType"])

    canonical_ticket = {
        # Identity and basic metadata
        "source": "jira",
        "ticket_id": issue.get("id"),
        "ticket_key": issue.get("key"),
        "title": fields.get("summary"),
        "issue_type": issue_type,
        "description": str(fields.get("description") or ""),

        # Status and people
        "status": get_nested_value(fields, ["status", "name"]),
        "priority": get_nested_value(fields, ["priority", "name"]),
        "assignee": get_nested_value(fields, ["assignee", "displayName"]),
        "reporter": reporter,
        "reporter_role": reporter_role,

        # Lifecycle timestamps
        "created_at": fields.get("created"),
        "updated_at": fields.get("updated"),
        "resolution": get_nested_value(fields, ["resolution", "name"]),
        "resolution_date": fields.get("resolutiondate"),

        # Classification hints
        "labels": labels,
        "is_L3": "L3" in (issue_type or ""),
        "customer_tier": customer_tier,

        # Project context
        "assigned_team": get_nested_value(fields, ["project", "name"]),
        "project_key": get_nested_value(fields, ["project", "key"]),
        "project_name": get_nested_value(fields, ["project", "name"]),
        "components": [c.get("name") for c in fields.get("components", [])],
        "environment": fields.get("environment"),

        # Placeholders for custom fields.
        # Populate these from Jira custom field IDs when they are configured,
        # or leave as None and inject them from an external source.
        "client_id": None,
        "contract_id": None,
        "m3_program_code": None,
        "function_area": None,
        "risk_level": None,
        "sensitive_system": None,
        "change_type": None,
        "emergency_change": None,
        "approver_list": None,
        "deployment_timestamp": None,
        "rollback_plan": None,
        "testing_evidence": None,
        "parent_project": None,

        # Nested collections. Filled by map_jira_bundle_to_canonical.
        "status_history": [],
        "comments": [],
        "worklogs": [],
        "approvals": [],
        "attachments": [],

        # External data injected before the rule engine runs.
        # Rules B and F read these; rules D use client_baseline.
        "contract": None,
        "rate_table": None,
        "client_baseline": None,
        "closed_periods": [],

        # Rule engine output. Every rule writes its result under this key
        # so that raw Jira fields are never overwritten.
        "rule_results": {},
    }

    return canonical_ticket


# ---------------------------------------------------------------------------
# Changelog -> status history
# ---------------------------------------------------------------------------

def map_status_history(changelog):
    """
    Convert a Jira changelog into a sorted list of status transitions.

    Only entries where the changed field is "status" are kept. Each entry
    records the ticket state before and after the transition, plus the
    history ID so the event can be deduplicated downstream.

    Args:
        changelog: Either the list returned by the changelog endpoint, or
                   a raw response dict containing a "values" key.

    Returns:
        A list of status-change dicts sorted by creation time.
    """
    if isinstance(changelog, dict):
        changelog = changelog.get("values", [])

    status_changes = []

    for changelog_entry in changelog or []:
        author = get_nested_value(changelog_entry, ["author", "displayName"])
        created = changelog_entry.get("created")

        for changed_item in changelog_entry.get("items", []):
            if changed_item.get("field") != "status":
                continue

            status_changes.append({
                "history_id": changelog_entry.get("id"),
                "author": author,
                "created": created,
                "from": changed_item.get("fromString"),
                "to": changed_item.get("toString"),
            })

    status_changes.sort(key=lambda entry: entry.get("created") or "")
    return status_changes


def enrich_status_history(ticket):
    """
    Add duration and reopen flags to each status change on the ticket.

    Duration is attributed to the *previous* status: for the first entry,
    the duration is measured from ticket creation; for later entries, from
    the previous status change.

    A "reopen" is a transition from a terminal status (Resolved, Closed,
    Done) back to a non-terminal one.

    This function enriches the status_history entries themselves. The
    reopen *count* is produced by rule D-03, not here, so that all
    rule_results come from the rule engine.

    Mutates the ticket in place and returns it.
    """
    history = ticket.get("status_history", [])
    created_at = ticket.get("created_at")

    terminal_statuses = {"Resolved", "Closed", "Done"}

    if not history:
        return ticket

    for index, entry in enumerate(history):
        # Time spent in the previous status.
        previous_time = created_at if index == 0 else history[index - 1]["created"]
        entry["duration_in_previous_status_seconds"] = _seconds_between(
            previous_time, entry["created"]
        )

        # A reopen is a terminal -> non-terminal transition.
        if index > 0:
            previous_status = history[index - 1].get("to")
            current_status = entry.get("to")
            is_reopen = (
                previous_status in terminal_statuses
                and current_status not in terminal_statuses
            )
        else:
            is_reopen = False

        entry["is_reopen"] = is_reopen

    return ticket


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------

def map_comments(comments):
    """
    Map raw Jira comment payloads to the canonical comment shape.

    Accepts either a list or the raw response dict with a "comments" key.
    Each comment records its ID so that re-processing merges instead of
    duplicating.
    """
    if isinstance(comments, dict):
        comments = comments.get("comments", [])

    mapped_comments = []

    for raw_comment in comments or []:
        mapped_comments.append({
            "comment_id": raw_comment.get("id"),
            "author": get_nested_value(raw_comment, ["author", "displayName"]),
            "body": str(raw_comment.get("body") or ""),
            "created": raw_comment.get("created"),
            "updated": raw_comment.get("updated"),
            "is_internal": _is_internal_comment(raw_comment),
        })

    return mapped_comments


def _is_internal_comment(comment):
    """
    Return True if the comment is internal (not visible to the reporter).

    Jira Service Management marks public comments with `jsdPublic`. Classic
    Jira uses a `visibility` block instead. Both are handled here.
    """
    if "jsdPublic" in comment:
        return not comment.get("jsdPublic", True)
    if comment.get("visibility"):
        return True
    return False


# ---------------------------------------------------------------------------
# Worklogs
# ---------------------------------------------------------------------------

def map_worklogs(worklogs):
    """
    Map raw Jira worklog payloads to the canonical worklog shape.

    Worklogs carry the effort data that rules B and F depend on. Each
    worklog records its own ID so that reprocessing is idempotent.
    """
    if isinstance(worklogs, dict):
        worklogs = worklogs.get("worklogs", [])

    mapped_worklogs = []

    for raw_worklog in worklogs or []:
        mapped_worklogs.append({
            "worklog_id": raw_worklog.get("id"),
            "author": get_nested_value(raw_worklog, ["author", "displayName"]),
            "author_role": get_nested_value(raw_worklog, ["author", "accountType"]),
            "time_spent_seconds": raw_worklog.get("timeSpentSeconds"),
            "started": raw_worklog.get("started"),
            "comment": str(raw_worklog.get("comment") or ""),
        })

    return mapped_worklogs


# ---------------------------------------------------------------------------
# Approvals (Jira Service Management only)
# ---------------------------------------------------------------------------

def map_approvals(approvals):
    """
    Map raw JSM approval payloads to the canonical approval shape.

    Returns an empty list when approvals are not available. Rule set G
    treats missing approvals as a finding, not as an error, so this
    function never raises.
    """
    if not approvals:
        return []

    if isinstance(approvals, dict):
        approvals = approvals.get("values", [])

    mapped_approvals = []

    for raw_approval in approvals or []:
        mapped_approvals.append({
            "approval_id": raw_approval.get("id"),
            "approver": get_nested_value(raw_approval, ["approver", "displayName"]),
            "status": raw_approval.get("status"),
            "created": raw_approval.get("createdDate"),
            "decision": raw_approval.get("decision"),
        })

    return mapped_approvals


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def map_attachments(issue):
    """
    Map attachments from a Jira issue payload to the canonical shape.

    Attachments matter for rule set G, where test evidence and rollback
    plans are checked as part of the audit trail.
    """
    fields = issue.get("fields", {})
    attachments = fields.get("attachment") or []

    mapped_attachments = []

    for raw_attachment in attachments:
        mapped_attachments.append({
            "attachment_id": raw_attachment.get("id"),
            "filename": raw_attachment.get("filename"),
            "created": raw_attachment.get("created"),
            "author": get_nested_value(raw_attachment, ["author", "displayName"]),
            "size": raw_attachment.get("size"),
        })

    return mapped_attachments


# ---------------------------------------------------------------------------
# Bundle mapper
# ---------------------------------------------------------------------------

def map_jira_bundle_to_canonical(bundle):
    """
    Map a complete Jira bundle to a canonical ticket.

    A bundle is the search result for one issue plus every per-issue
    endpoint the connector fetched for it:

        bundle = {
            "issue":     <one item from search issues>,
            "changelog": <list from get_issue_changelog>,
            "comments":  <list from get_issue_comments>,
            "worklogs":  <list from get_issue_worklogs>,
            "approvals": <optional list from get_issue_approvals>,
        }

    The returned ticket is ready for external data injection and for the
    rule engine to run against.
    """
    issue = bundle.get("issue", {})

    ticket = map_jira_issue_to_canonical(issue)
    ticket["status_history"] = map_status_history(bundle.get("changelog", []))
    ticket["comments"] = map_comments(bundle.get("comments", []))
    ticket["worklogs"] = map_worklogs(bundle.get("worklogs", []))
    ticket["approvals"] = map_approvals(bundle.get("approvals", []))
    ticket["attachments"] = map_attachments(issue)

    enrich_status_history(ticket)

    return ticket


def map_jira_bundles_to_canonical(bundles):
    """
    Map a list of Jira bundles to canonical tickets.

    Preserves input order so callers can align output with input.
    """
    return [map_jira_bundle_to_canonical(bundle) for bundle in bundles]


# ---------------------------------------------------------------------------
# Backwards compatible search-only mapper
# ---------------------------------------------------------------------------

def map_jira_response_to_canonical(response):
    """
    Map a Jira search response to canonical tickets without fetching
    per-issue history.

    This is a fallback for callers that only have the search result. It
    does not populate status_history, comments, worklogs, approvals, or
    attachments. Prefer `map_jira_bundles_to_canonical` for full data.
    """
    issues = response.get("issues", [])
    return [map_jira_issue_to_canonical(issue) for issue in issues]