"""
Full-sync pipeline for Jira.

This module fetches every issue the API user can see, fetches the full
history for each one, maps the results to canonical tickets, runs the
rule engine, and writes the result to a dedicated JSON file.

It is intentionally separate from the incremental poller:

  - The incremental poller runs every 5 minutes and pulls only issues
    updated in the last 10 minutes.
  - The full sync pulls everything and is meant to run manually, nightly,
    or on demand.

They share the connector, the mapper, and the rule engine. They write to
different output files so they never race each other.
"""

import asyncio
import json
from pathlib import Path

from fastapi import HTTPException

from app.connectors.Jira_API_connector import search_all_issues, fetch_full_bundle
from app.mappers.jira_mapper import map_jira_bundles_to_canonical
from app.mappers.jira_rule_engine import transform_canonical_tickets_full


# ---------------------------------------------------------------------------
# Output location
# ---------------------------------------------------------------------------
# Full sync writes to its own file so it never races the incremental poller.
# Adjust parents[N] to match your repo layout if the folder structure moves.
# ---------------------------------------------------------------------------

FULL_SYNC_OUTPUT_FOLDER = Path(__file__).resolve().parents[3] / "local_data" / "output"
FULL_SYNC_OUTPUT_FILE = FULL_SYNC_OUTPUT_FOLDER / "jira_issues.json"

# Set to True only if your Jira instance is Jira Service Management.
# Otherwise fetch_full_bundle returns an empty approvals list.
FETCH_APPROVALS = True


# ---------------------------------------------------------------------------
# Concurrency guard
# ---------------------------------------------------------------------------
# Prevents two full syncs from running at the same time, whether triggered
# by the endpoint, the nightly poller, or manual invocation. Concurrent
# runs would both write to the same JSON file and the last writer wins.
# ---------------------------------------------------------------------------

_full_sync_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# External data injection
# ---------------------------------------------------------------------------

def inject_external_data(tickets):
    """
    Attach external data that rules B, D, and F expect on every ticket.

    The rule engine does not fetch external data itself; it only reads
    what is already on the ticket. This function is the single place
    where that data is attached.

    Replace the placeholder values below with real lookups when the
    corresponding data sources are wired in:

        contract         - from the contract store (used by B, F)
        rate_table       - from the finance rate table (used by F)
        client_baseline  - computed from historical tickets (used by D)
        closed_periods   - from finance periods (used by F-04)

    Args:
        tickets: List of canonical tickets.

    Returns:
        The same list with the external fields set on every ticket.
    """
    for ticket in tickets:
        ticket.setdefault("contract", None)
        ticket.setdefault("rate_table", None)
        ticket.setdefault("client_baseline", None)
        ticket.setdefault("closed_periods", [])
    return tickets


# ---------------------------------------------------------------------------
# Merge helpers
# ---------------------------------------------------------------------------

def _load_existing(output_file: Path) -> list:
    """
    Load the existing ticket list from disk.

    Returns an empty list if the file is missing or contains invalid JSON,
    so the caller can treat a first run and a corrupt file the same way.
    """
    if not output_file.exists():
        return []
    try:
        data = json.loads(output_file.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _merge_by_ticket_key(existing: list, incoming: list) -> list:
    """
    Merge incoming tickets onto existing tickets by ticket_key.

    Incoming tickets overwrite existing ones with the same key. Order in
    the output is not guaranteed; callers that need ordering should sort
    after merging.
    """
    ticket_by_key = {
        ticket.get("ticket_key"): ticket
        for ticket in existing
        if isinstance(ticket, dict) and ticket.get("ticket_key")
    }

    for ticket in incoming:
        key = ticket.get("ticket_key")
        if key:
            ticket_by_key[key] = ticket

    return list(ticket_by_key.values())


# ---------------------------------------------------------------------------
# Full sync
# ---------------------------------------------------------------------------

async def full_sync_jira(
    rule: str | None = None,
    output_file: Path | None = None,
):
    """
    Fetch every issue the API user can see and run the full pipeline.

    Steps:
        1. Search Jira for every issue the API user can access.
        2. Fetch changelog, comments, worklogs, and approvals per issue.
        3. Map the bundles to canonical tickets.
        4. Inject external data before rules run.
        5. Run the rule engine (default: ALL rule sets).
        6. Merge with any existing output file by ticket_key.
        7. Write the merged list to disk.

    Args:
        rule: Optional rule set name. None runs every rule set.
        output_file: Optional override for the output path. Defaults to
            FULL_SYNC_OUTPUT_FILE.

    Returns:
        The final list of tickets (not the merged file contents).

    Raises:
        HTTPException(409) if another full sync is already running.
        HTTPException(500) if any step fails.
    """
    if _full_sync_lock.locked():
        raise HTTPException(status_code=409, detail="Full sync already running")

    async with _full_sync_lock:
        target = Path(output_file) if output_file else FULL_SYNC_OUTPUT_FILE
        target.parent.mkdir(parents=True, exist_ok=True)

        print(f"[full sync] starting. Output: {target.resolve()}")

        try:
            # 1. Fetch every issue the API user can see.
            issues = await search_all_issues()
            print(f"[full sync] search returned {len(issues)} issues")

            # 2. Fetch full history for each issue.
            #    Progress is logged every 50 issues so long runs are visible.
            bundles = []
            for index, issue in enumerate(issues, start=1):
                bundle = await fetch_full_bundle(issue)
                if not FETCH_APPROVALS:
                    bundle["approvals"] = []
                bundles.append(bundle)

                if index % 50 == 0:
                    print(f"[full sync] fetched history for {index}/{len(issues)}")

            # 3. Map to canonical tickets.
            canonical_tickets = map_jira_bundles_to_canonical(bundles)
            print(f"[full sync] mapped {len(canonical_tickets)} canonical tickets")

            # 4. Inject external data before rules run.
            canonical_tickets = inject_external_data(canonical_tickets)

            # 5. Run the rule engine.
            #    rule=None means "ALL": A, B, C, D, F, G in dependency order.
            final_tickets = transform_canonical_tickets_full(
                canonical_tickets,
                rule,
            )
            print(f"[full sync] rules applied to {len(final_tickets)} tickets")

            # 6. Merge with existing output (idempotent by ticket_key).
            existing_tickets = _load_existing(target)
            merged_tickets = _merge_by_ticket_key(existing_tickets, final_tickets)

            # 7. Write.
            target.write_text(
                json.dumps(merged_tickets, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            print(
                f"[full sync] wrote {len(merged_tickets)} tickets to {target.resolve()}"
            )
            return final_tickets

        except HTTPException:
            # Already an HTTP error with meaningful status and detail.
            raise
        except Exception as exception:
            raise HTTPException(
                status_code=500,
                detail=f"Jira full sync failed: {str(exception)}",
            )


# ---------------------------------------------------------------------------
# Full sync poller
# ---------------------------------------------------------------------------

async def jira_full_sync_poller(
    interval_hours: int = 24,
    initial_delay_seconds: int = 0,
):
    """
    Run the full sync on a fixed interval.

    Use this only for slow schedules (nightly or longer). Do not use it
    for the 5-minute incremental poll.

    Args:
        interval_hours: Hours between full sync runs.
        initial_delay_seconds: Delay before the first run. Use this to
            avoid a full sync firing on every app startup during dev
            reloads or container restarts.
    """
    if initial_delay_seconds > 0:
        print(f"[full sync] first run delayed by {initial_delay_seconds}s")
        await asyncio.sleep(initial_delay_seconds)

    while True:
        try:
            await full_sync_jira()
        except Exception as exception:
            # Keep the poller alive. A failure tonight should not prevent
            print(f"[full sync] error: {exception}")

        print(f"[full sync] sleeping for {interval_hours}h")
        await asyncio.sleep(interval_hours * 3600)


# ---------------------------------------------------------------------------
# Manual entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    asyncio.run(full_sync_jira())