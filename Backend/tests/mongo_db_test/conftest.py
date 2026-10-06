# tests/mongo/conftest.py

import pytest
import pytest_asyncio

from app.outputs.MongoDB.mongo_db_output import init_mongo, close_mongo, get_db
from app.outputs.MongoDB.mongo_db_common_func import persist


# A key prefix used by every test in this folder so cleanup only touches
# rows this suite created. Real data is never deleted.
TEST_KEY_PREFIX = "PYTEST-"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def mongo_session():
    """
    Ensure Mongo is initialised once for the whole test session.

    The session scope means indexes are created once, not per test.
    """
    await init_mongo()
    yield
    await close_mongo()


@pytest_asyncio.fixture(autouse=True)
async def clean_test_data():
    """
    Delete any document whose identity starts with TEST_KEY_PREFIX
    before and after each test. Keeps tests independent.
    """
    db = get_db()

    async def _cleanup():
        await db.jira_tickets.delete_many(
            {"ticket_key": {"$regex": f"^{TEST_KEY_PREFIX}"}}
        )
        await db.document_events.delete_many(
            {"document_id": {"$regex": f"^{TEST_KEY_PREFIX}"}}
        )

    await _cleanup()
    yield
    await _cleanup()


@pytest.fixture
def fake_ticket():
    """
    Return a factory that builds a canonical Jira ticket for testing.
    Keys are prefixed so cleanup can identify them.
    """
    def _make(ticket_key="PYTEST-1", **overrides):
        ticket = {
            "source": "jira",
            "ticket_key": ticket_key,
            "ticket_id": "99999",
            "title": "Fake ticket for testing",
            "description": "Testing the write path without touching Jira.",
            "status": "In Progress",
            "priority": "Medium",
            "client_id": "CLIENT-A",
            "function_area": "Warehouse",
            "created_at": "2026-09-23T10:00:00+0000",
            "updated_at": "2026-09-23T11:00:00+0000",
            "status_history": [
                {
                    "history_id": "1",
                    "author": "Jane",
                    "created": "2026-09-23T10:05:00+0000",
                    "from": "Open",
                    "to": "In Progress",
                    "duration_in_previous_status_seconds": 300,
                    "is_reopen": False,
                }
            ],
            "comments": [
                {
                    "comment_id": "c1",
                    "author": "Jane",
                    "body": "This is a test comment.",
                    "body_clean": "This is a test comment.",
                    "created": "2026-09-23T10:10:00+0000",
                    "updated": "2026-09-23T10:10:00+0000",
                    "is_internal": False,
                }
            ],
            "worklogs": [
                {
                    "worklog_id": "w1",
                    "author": "John",
                    "author_role": "Consultant",
                    "time_spent_seconds": 3600,
                    "started": "2026-09-23T10:30:00+0000",
                    "comment": "",
                }
            ],
            "attachments": [],
            "approvals": [],
            "rule_results": {},
        }
        ticket.update(overrides)
        return ticket

    return _make