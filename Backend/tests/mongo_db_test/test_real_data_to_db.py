# tests/jira_integration/test_real_jira_to_mongo.py

"""
Integration tests that hit the real Jira API and write to Mongo.

These tests are skipped by default. Run them explicitly with:

    pytest tests/jira_integration -m integration -v

They require:
    - valid Jira credentials in the environment
    - a reachable Mongo instance
    - at least one issue in the configured Jira project

Keep this folder small. It exists to prove the connector -> mapper ->
rules -> Mongo chain works against real data, not to cover every rule.
"""

import pytest

from app.connectors.Jira_API_connector import search_all_issues, fetch_full_bundle
from app.mappers.jira_mapper import map_jira_bundles_to_canonical
from app.mappers.jira_rule_engine import transform_canonical_tickets_full
from app.outputs.MongoDB.mongo_db_common_func import persist
from app.outputs.MongoDB.mongo_db_output import get_db


pytestmark = pytest.mark.integration


async def _fetch_small_batch(limit=3):
    """Fetch a small batch of real Jira issues and run them through the pipeline."""
    issues = await search_all_issues("project = EMAL ORDER BY created DESC")
    issues = issues[:limit]

    bundles = [await fetch_full_bundle(i) for i in issues]
    canonical = map_jira_bundles_to_canonical(bundles)
    return transform_canonical_tickets_full(canonical, "ALL")


@pytest.mark.asyncio
async def test_real_ticket_reaches_mongo():
    tickets = await _fetch_small_batch(limit=1)
    if not tickets:
        pytest.skip("No Jira issues found in the configured project")

    summary = await persist("jira", tickets)
    assert summary["inserted"] + summary["matched"] + summary["modified"] == 1


@pytest.mark.asyncio
async def test_real_ticket_has_rule_results():
    tickets = await _fetch_small_batch(limit=1)
    if not tickets:
        pytest.skip("No Jira issues found")

    await persist("jira", tickets)
    key = tickets[0]["ticket_key"]

    db = get_db()
    doc = await db.jira_tickets.find_one({"ticket_key": key})

    assert doc is not None
    assert "rule_results" in doc
    # If rule results are empty, the rule engine did not run.
    # This is the check that catches the apply_rule_set bug.
    assert doc["rule_results"], "rule_results is empty — rules did not run"


@pytest.mark.asyncio
async def test_real_ticket_is_idempotent():
    tickets = await _fetch_small_batch(limit=1)
    if not tickets:
        pytest.skip("No Jira issues found")

    key = tickets[0]["ticket_key"]
    db = get_db()

    await persist("jira", tickets)
    events_first = await db.document_events.count_documents({"document_id": key})

    await persist("jira", tickets)
    events_second = await db.document_events.count_documents({"document_id": key})

    assert events_first == events_second