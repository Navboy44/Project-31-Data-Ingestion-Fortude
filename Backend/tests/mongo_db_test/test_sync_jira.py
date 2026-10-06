# scripts/test_sync_one_project.py

import asyncio
from app.outputs.MongoDB.mongo_db_output import init_mongo, close_mongo, get_db
from app.outputs.MongoDB.mongo_db_common_func import persist
from app.connectors.Jira_API_connector import search_all_issues, fetch_full_bundle
from app.mappers.jira_mapper import map_jira_bundles_to_canonical
from app.mappers.jira_rule_engine import transform_canonical_tickets_full


async def main():
    await init_mongo()

    # Pull a small batch — use a JQL that limits to a few tickets
    issues = await search_all_issues("project = PROJ ORDER BY created DESC")
    issues = issues[:5]   # take only 5 for the test
    print(f"Fetched {len(issues)} issues")

    bundles = [await fetch_full_bundle(i) for i in issues]
    canonical = map_jira_bundles_to_canonical(bundles)
    final_tickets = transform_canonical_tickets_full(canonical, "ALL")

    summary = await persist("jira", final_tickets)
    print("persist summary:", summary)

    # Verify one landed
    db = get_db()
    first_key = issues[0]["key"]
    doc = await db.jira_tickets.find_one({"ticket_key": first_key})
    print(f"\n{first_key} found in Mongo:", doc is not None)
    if doc:
        print("  title:", doc.get("title"))
        print("  function_area:", doc.get("function_area"))
        print("  comments:", len(doc.get("comments", [])))
        print("  status_history:", len(doc.get("status_history", [])))
        print("  rule_results keys:", list((doc.get("rule_results") or {}).keys())[:8])

    await close_mongo()


if __name__ == "__main__":
    asyncio.run(main())