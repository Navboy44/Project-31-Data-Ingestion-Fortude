"""
Jira REST API connector.

Single place that knows how to talk to Jira. Every function in this
module either fetches data from Jira or raises an HTTPException that
FastAPI can surface to the caller. No other module in the pipeline
issues HTTP requests to Jira.

Endpoints used
--------------
- POST /rest/api/3/search/jql           incremental and full search
- GET  /rest/api/3/field                field metadata (custom field IDs)
- GET  /rest/api/3/issue/{key}/changelog
- GET  /rest/api/3/issue/{key}/comment
- GET  /rest/api/3/issue/{key}/worklog
- GET  /rest/servicedeskapi/request/{key}/approval   (JSM only)

Error handling
--------------
All functions raise `HTTPException` on failure so that FastAPI can
return a proper response. Non-JSM endpoints propagate the HTTP status
from Jira; the JSM approvals endpoint swallows errors and returns an
empty list because JSM is optional.

Authentication
--------------
All requests use HTTP Basic auth built from JIRA_EMAIL and
JIRA_API_TOKEN in connector_config.
"""

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from app.connector_config import JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN


# How far back the incremental poller looks. The poll runs every 5
# minutes but fetches a 10-minute window, giving a 2x overlap so a
# missed run does not create a gap.
FREQUENTLY_UPDATED_RANGE_MINS = "10"


class JiraSearch(BaseModel):
    """Request body for a Jira search. Used by FastAPI routes, if any."""
    jql: str
    max_results: int = 50


def auth_header() -> httpx.BasicAuth:
    """
    Return the HTTP Basic auth object used for every Jira request.

    Reads credentials from connector_config so no function in this
    module needs to know where they come from.
    """
    return httpx.BasicAuth(JIRA_EMAIL, JIRA_API_TOKEN)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def get_recently_created_issues():
    """
    Fetch issues updated in the last FREQUENTLY_UPDATED_RANGE_MINS minutes.

    Used by the incremental poller. The lookback window is larger than
    the poll interval so consecutive polls overlap, which is what makes
    the pipeline resilient to a missed run.

    Returns:
        The raw search response dict with an "issues" key.

    Raises:
        HTTPException with Jira's status code and body on failure.
    """
    url = f"{JIRA_BASE_URL}rest/api/3/search/jql"
    jql = f"updated >= -{FREQUENTLY_UPDATED_RANGE_MINS}m ORDER BY updated ASC"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    body = {
        "jql": jql,
        "maxResults": 100,
        "fields": ["*all"],
    }

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.post(
                url,
                json=body,
                auth=auth_header(),
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as exception:
            raise HTTPException(
                status_code=exception.response.status_code,
                detail=f"Jira API error: {exception.response.text}",
            )
        except Exception as exception:
            raise HTTPException(
                status_code=500,
                detail=f"Internal Server Error: {str(exception)}",
            )


async def search_all_issues(jql: str | None = None) -> list[dict]:
    """
    Fetch every issue matching the given JQL, with cursor pagination.

    Uses Jira Cloud's new search endpoint (POST /rest/api/3/search/jql),
    which returns a `nextPageToken` for pagination rather than a startAt
    offset.

    Args:
        jql: Optional JQL filter. When None, the default query matches
             every issue the API user can see. Pass a project-scoped
             query (e.g. "project = PROJ ORDER BY created DESC") to
             narrow the search for tests or targeted syncs.

    Returns:
        A list of raw Jira issue payloads. Empty list if nothing matches.
    """
    url = f"{JIRA_BASE_URL}rest/api/3/search/jql"

    # Default: every issue the API user can see, oldest update first.
    # Overridden by the caller when a narrower scope is needed.
    if not jql:
        jql = "project IS NOT EMPTY ORDER BY updated ASC"

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    issues = []
    next_token = None
    page = 0

    async with httpx.AsyncClient(timeout=120) as client:
        while True:
            body = {
                "jql": jql,
                "maxResults": 100,
                "fields": ["*all"],
            }
            if next_token:
                body["nextPageToken"] = next_token

            response = await client.post(
                url,
                json=body,
                auth=auth_header(),
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            batch = data.get("issues", [])
            issues.extend(batch)
            page += 1

            print(f"search page {page}: +{len(batch)} issues (total {len(issues)})")

            next_token = data.get("nextPageToken")
            if not next_token:
                break

    return issues


# ---------------------------------------------------------------------------
# Field metadata
# ---------------------------------------------------------------------------

async def get_jira_fields():
    """
    Fetch every field definition on this Jira instance.

    Used to discover custom field IDs (the "customfield_XXXXX" names)
    before mapping them to canonical ticket fields such as client_id
    or m3_program_code.

    Returns:
        A list of field definitions as returned by Jira.

    Raises:
        HTTPException with Jira's status code and body on failure.
    """
    url = f"{JIRA_BASE_URL}rest/api/3/field"

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            response = await client.get(
                url,
                auth=auth_header(),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as exception:
            raise HTTPException(
                status_code=exception.response.status_code,
                detail=f"Jira API error: {exception.response.text}",
            )
        except Exception as exception:
            raise HTTPException(
                status_code=500,
                detail=f"Internal Server Error: {str(exception)}",
            )


# ---------------------------------------------------------------------------
# Per-issue history
# ---------------------------------------------------------------------------
# These three endpoints share the same pagination pattern: the classic
# Jira offset pagination with startAt / maxResults / total. They are
# written out separately rather than parameterised because the response
# field name differs ("values", "comments", "worklogs") and the
# readability is worth the small duplication.
# ---------------------------------------------------------------------------

async def get_issue_changelog(issue_key: str) -> list[dict]:
    """
    Fetch the full change history for one issue.

    This is what makes SLA, reopen, and audit rules possible. Current
    ticket state alone cannot answer "how long was it in each status"
    or "was the approval recorded before deployment".

    Args:
        issue_key: Jira issue key, e.g. "PROJ-123".

    Returns:
        A list of changelog entries. Each entry has "id", "author",
        "created", and an "items" list describing what changed.
    """
    url = f"{JIRA_BASE_URL}rest/api/3/issue/{issue_key}/changelog"
    changelog_entries = []
    start_at = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            response = await client.get(
                url,
                params={"startAt": start_at, "maxResults": 100},
                auth=auth_header(),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            batch = data.get("values", [])
            changelog_entries.extend(batch)

            # Jira returns the total count. Stop when we have them all.
            if start_at + len(batch) >= data.get("total", 0):
                break
            start_at += len(batch)

    return changelog_entries


async def get_issue_comments(issue_key: str) -> list[dict]:
    """
    Fetch every comment on one issue.

    Used for the knowledge base (problem/solution extraction), for
    detecting outbound client contact (SLA pause), and for scanning
    for sensitive content before storage.

    Args:
        issue_key: Jira issue key, e.g. "PROJ-123".

    Returns:
        A list of comment payloads, each with "id", "author", "body",
        "created", and "updated".
    """
    url = f"{JIRA_BASE_URL}rest/api/3/issue/{issue_key}/comment"
    comments = []
    start_at = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            response = await client.get(
                url,
                params={"startAt": start_at, "maxResults": 100},
                auth=auth_header(),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            batch = data.get("comments", [])
            comments.extend(batch)

            if start_at + len(batch) >= data.get("total", 0):
                break
            start_at += len(batch)

    return comments


async def get_issue_worklogs(issue_key: str) -> list[dict]:
    """
    Fetch every worklog on one issue.

    Worklogs carry the effort data that rule sets B (contract scope)
    and F (cost recovery) depend on. Each worklog has a stable ID so
    re-fetching the same issue does not duplicate entries.

    Args:
        issue_key: Jira issue key, e.g. "PROJ-123".

    Returns:
        A list of worklog payloads, each with "id", "author",
        "timeSpentSeconds", "started", and "comment".
    """
    url = f"{JIRA_BASE_URL}rest/api/3/issue/{issue_key}/worklog"
    worklogs = []
    start_at = 0

    async with httpx.AsyncClient(timeout=60) as client:
        while True:
            response = await client.get(
                url,
                params={"startAt": start_at, "maxResults": 100},
                auth=auth_header(),
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            batch = data.get("worklogs", [])
            worklogs.extend(batch)

            if start_at + len(batch) >= data.get("total", 0):
                break
            start_at += len(batch)

    return worklogs


# ---------------------------------------------------------------------------
# Approvals (Jira Service Management only)
# ---------------------------------------------------------------------------

async def get_issue_approvals(issue_key: str) -> list[dict]:
    """
    Fetch approvals for a Jira Service Management change request.

    Returns an empty list on any failure. JSM is optional, and most
    Jira instances are not JSM, so missing approvals are treated as
    "no approvals recorded" rather than an error. Rule set G treats
    a missing approval as an audit finding, not as a crash.

    Args:
        issue_key: Jira issue key, e.g. "PROJ-123".

    Returns:
        A list of approval payloads, or an empty list if the issue is
        not a JSM request, the endpoint is unavailable, or the request
        fails for any reason.
    """
    url = f"{JIRA_BASE_URL}rest/servicedeskapi/request/{issue_key}/approval"
    approvals = []
    start_at = 0

    async with httpx.AsyncClient(timeout=60) as client:
        try:
            while True:
                response = await client.get(
                    url,
                    params={"startAt": start_at, "limit": 100},
                    auth=auth_header(),
                    headers={"Accept": "application/json"},
                )

                # 400/403/404 mean "not a JSM request" or "no access".
                # Both are expected on non-JSM instances.
                if response.status_code in (400, 403, 404):
                    return []

                response.raise_for_status()
                data = response.json()

                batch = data.get("values", [])
                approvals.extend(batch)

                # JSM uses isLastPage instead of a total count.
                if data.get("isLastPage", True) or not batch:
                    break
                start_at += len(batch)

        except Exception:
            return []

    return approvals


# ---------------------------------------------------------------------------
# Bundle fetch
# ---------------------------------------------------------------------------

async def fetch_full_bundle(issue: dict) -> dict:
    """
    Fetch every per-issue endpoint for one issue and return them together.

    Bundles the search result with its changelog, comments, worklogs,
    and approvals so the mapper can build a complete canonical ticket
    from a single object. This is the only function callers need in
    order to gather everything about one issue.

    Args:
        issue: One item from the "issues" list returned by
               search_all_issues or get_recently_updated_issues.

    Returns:
        A dict with keys:
            issue       raw search result
            changelog   list of status/field change entries
            comments    list of comment payloads
            worklogs    list of worklog payloads
            approvals   list of approval payloads (empty on non-JSM)
    """
    key = issue["key"]

    return {
        "issue": issue,
        "changelog": await get_issue_changelog(key),
        "comments": await get_issue_comments(key),
        "worklogs": await get_issue_worklogs(key),
        "approvals": await get_issue_approvals(key),
    }