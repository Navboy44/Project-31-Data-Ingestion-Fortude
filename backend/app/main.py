import asyncio
import json
import logging

# Import Jira utilities directly from the project root
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, model_validator
from typing import Literal
import re

from app.connectors.Infor_API_connector import (
    fetch_order_lines,
    router as infor_router,
    setting as infor_setting,
)
from app.mappers.infor_mapper import map_infor_response


from app import auth
from app.connectors.config_db import (
    PipelineDuplicateNameError,
    add_connector,
    add_history_entry,
    add_output,
    add_pipeline,
    add_rule,
    clear_sharepoint_delta_link,
    delete_connector,
    delete_history_entry,
    delete_output,
    delete_pipeline,
    delete_rule,
    get_pipeline,
    get_sharepoint_delta_link,
    get_sharepoint_item_mappings,
    init_config_db,
    list_connectors,
    list_history,
    list_outputs,
    list_pipelines,
    list_rules,
    save_sharepoint_sync_state,
    update_pipeline,
)
from app.connectors.local_folder_connector import read_local_text_files
from app.connectors.sharepoint_connector import (
    SharePointDeltaStateError,
    get_sharepoint_drive_id,
    read_sharepoint_delta,
)

from rules.rule_handlers import apply_selected_rules
import auth
from connectors.connectors_db import (
    init_config_db,
    list_connectors,
    add_connector,
    delete_connector,
    list_rules,
    add_rule,
    delete_rule,
    list_outputs,
    add_output,
    delete_output,
    add_history_entry,
    list_history,
    delete_history_entry,
    get_sharepoint_delta_link,
    clear_sharepoint_delta_link,
    get_sharepoint_item_mappings,
    save_sharepoint_sync_state,
)
from fastapi import BackgroundTasks
# Import Jira utilities directly from the project root
from connectors.Jira_API_connector import get_my_issues,get_jira_fields
from mappers.jira_mapper import map_jira_response_to_canonical
from mappers.jira_transformer import transform_canonical_tickets_for_l3
from outputs.kafka_output import publish_documents as publish_kafka_documents
from outputs.qdrant_output import publish_documents as publish_qdrant_documents
from app.mappers.local_file_mapper import map_local_files_to_canonical
from app.outputs.MongoDB.mongo_db_common_func import persist
from app.outputs.MongoDB.source_registration_table import SOURCES
from app.rules.rule_handlers import apply_selected_rules
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, StrictInt

import sys
sys.path.append('.')

import sqlite3

from app.connectors.Jira_API_connector import (
    fetch_full_bundle,
    get_recently_created_issues,
)
from app.mappers.jira_full_sync import full_sync_jira, jira_full_sync_poller
from app.mappers.jira_mapper import map_jira_bundles_to_canonical
from app.mappers.jira_rule_engine import transform_canonical_tickets_full

from app.connectors.Infor_API_connector import router as infor_router
from app import connector_config

BASE_FOLDER = Path(__file__).resolve().parents[2]
OUTPUT_FOLDER = BASE_FOLDER / "local_data" / "output"
INPUT_FOLDER = BASE_FOLDER / "local_data" / "input"

# BASE_FOLDER = Path(__file__).resolve().parents[2]
# OUTPUT_FOLDER = BASE_FOLDER / "local_data" / "output"
POLL_INTERVAL_SECONDS = 300
JIRA_FULL_SYNC_INTERVAL_HOURS = 24
JIRA_FULL_SYNC_DELAY_SECONDS = 0  # JIRA_FULL_SYNC_INTERVAL_HOURS in seconds
SHAREPOINT_POLL_RULE = "Knowledge Base Rules"

logger = logging.getLogger(__name__)
ingestion_lock = threading.Lock()
polling_task = None


# ---------------------------------------------------------------------------
# Lifespan - initialise databases once on startup
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global polling_task
    auth.init_db()
    init_config_db()
    app.state.client = httpx.AsyncClient(timeout=30.0)
    polling_task = asyncio.create_task(poll_sharepoint_ingestion())
    jira_full_sync_task = asyncio.create_task(
        jira_full_sync_poller(
            interval_hours=JIRA_FULL_SYNC_INTERVAL_HOURS,
            initial_delay_seconds=JIRA_FULL_SYNC_DELAY_SECONDS,
        )
    )

    try:
        yield
    finally:
        await app.state.client.aclose()
        for task in (polling_task, jira_full_sync_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        polling_task = None

        jira_full_sync_task = None


app = FastAPI(lifespan=lifespan)
app.include_router(infor_router)  # registering infor router

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class IngestionRequest(BaseModel):
    connector: str
    rule: str | None = None
    mapper: str | None = None
    outputs: str | None = None
    order_type: Literal["purchase", "customer"] | None = None
    order_number: str | None = None

    @model_validator(mode="after")
    def validate_infor_order(self):
        if "infor" in self.connector.lower():
            if self.order_type is None or not self.order_number:
                raise ValueError("Infor requires an order type and order number.")

            self.order_number = self.order_number.strip()

            if not re.fullmatch(r"[A-Za-z0-9_-]{1,50}", self.order_number):
                raise ValueError(
                    "Order number must contain 1-50 letters, digits, "
                    "underscores or hyphens."
                )

        return self


class ConfigItemCreate(BaseModel):
    name: str


def publish_selected_outputs(documents, selected_outputs: str | None):
    """Send documents to each selected output target."""
    output_names = {
        output.strip().lower()
        for output in (selected_outputs or "").split(",")
        if output.strip()
    }
    if "kafka" in output_names:
        publish_kafka_documents(documents)
    if "vector database" in output_names:
        publish_qdrant_documents(documents)

class IngestRequest(BaseModel):
    """A batch of documents for one registered source."""

    source: str
    documents: list[dict]


class IngestResponse(BaseModel):
    source: str
    inserted: int
    modified: int
    matched: int
    skipped: int
    events_appended: int


class PipelineSave(BaseModel):
    """Complete definition used for both creating and editing a pipeline."""

    name: str
    connector_id: StrictInt
    rule_ids: list[StrictInt]
    output_ids: list[StrictInt]


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}


def run_sharepoint_ingestion(rule, selected_outputs=None):
    """Synchronize SharePoint changes for both manual and automatic triggers."""
    with ingestion_lock:
        OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

        drive_id = get_sharepoint_drive_id()
        previous_delta_link = get_sharepoint_delta_link(drive_id)
        try:
            delta_result = read_sharepoint_delta(previous_delta_link)
        except SharePointDeltaStateError:
            clear_sharepoint_delta_link(drive_id)
            previous_delta_link = None
            delta_result = read_sharepoint_delta()

        mappings = get_sharepoint_item_mappings(drive_id)
        mapping_upserts = {}
        mapping_deletes = set()
        processed_documents = []
        processed = 0
        seen_item_ids = set()

        for change in delta_result["changes"]:
            item_id = change["item_id"]
            seen_item_ids.add(item_id)
            previous_output_name = mappings.get(item_id)

            if change["deleted"] or not change["supported"]:
                if previous_output_name:
                    (OUTPUT_FOLDER / previous_output_name).unlink(missing_ok=True)
                    mapping_deletes.add(item_id)
                continue

            document = map_local_files_to_canonical([change["record"]])[0]
            document = apply_selected_rules(document, rule)
            processed_documents.append(document)
            output_name = Path(document["file_name"]).with_suffix(".json").name
            if previous_output_name and previous_output_name != output_name:
                (OUTPUT_FOLDER / previous_output_name).unlink(missing_ok=True)
            (OUTPUT_FOLDER / output_name).write_text(
                json.dumps(document, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            mapping_upserts[item_id] = output_name
            processed += 1

        # A fresh enumeration is authoritative, so remove stale tracked items.
        if previous_delta_link is None:
            for item_id, output_name in mappings.items():
                if item_id not in seen_item_ids:
                    (OUTPUT_FOLDER / output_name).unlink(missing_ok=True)
                    mapping_deletes.add(item_id)

        save_sharepoint_sync_state(
            drive_id,
            delta_result["delta_link"],
            mapping_upserts,
            mapping_deletes,
        )
        publish_selected_outputs(processed_documents, selected_outputs)

        return {
            "status": "success",
            "processed": processed,
            "rule": rule,
        }


async def poll_sharepoint_ingestion():
    while True:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        try:
            await asyncio.to_thread(run_sharepoint_ingestion, SHAREPOINT_POLL_RULE)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Automatic SharePoint ingestion failed")

async def poll_jira(rule: str, selected_outputs=None):
    """Polls Jira every 5 minutes, transforms data, and saves to JSON."""

async def poll_jira(rule: str | None = None):
    """
    Polls Jira every 5 minutes, transforms data, and saves to JSON.
    Defaults to running ALL rule sets (A, B, C, D, F, G).
    Pass a specific rule ("A", "B", "C", "D", "F", "G")
    to run only that rule set.
    """
    while True:
        print(f"Polling Jira... (using rule: {rule or 'ALL'})")
        try:
            jira_data = await get_recently_created_issues()
            print(f"Fetched {len(jira_data.get('issues', []))} issues from Jira.")
            issues = jira_data.get("issues", [])

            bundles = []
            for issue in issues:
                bundles.append(await fetch_full_bundle(issue))

            canonical_tickets = map_jira_bundles_to_canonical(bundles)
            print(f"Mapped {len(canonical_tickets)} canonical tickets from Jira.")
            final_tickets = transform_canonical_tickets_full(
                canonical_tickets,
                rule,
            )

            OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
            output_file = OUTPUT_FOLDER / "jira_issues.json"

            existing_tickets = []
            if output_file.exists():
                try:
                    existing_tickets = json.loads(
                        output_file.read_text(encoding="utf-8")
                    )
                except json.JSONDecodeError:
                    pass

            ticket_dict = {
                t.get("ticket_key"): t
                for t in existing_tickets
                if isinstance(t, dict) and t.get("ticket_key")
            }

            for t in final_tickets:
                key = t.get("ticket_key")
                if key:
                    ticket_dict[key] = t

            merged_tickets = list(ticket_dict.values())

            output_file.write_text(
                json.dumps(merged_tickets, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            print(
                f"Updated {output_file.name}. "
                f"Rule set: {rule or 'ALL'}. Total tickets: {len(merged_tickets)}"
            )

        except Exception as e:
            print(f"Error polling Jira: {e}")

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


# fully sync jira issues and run all rules on them
@app.post("/jira/full-sync")
async def trigger_full_sync(projects: list[str] | None = None):
    tickets = await full_sync_jira(projects=projects)
    return {"count": len(tickets)}


@app.post("/api/ingest/local-folder")
async def ingest_local_folder(
    request: IngestionRequest, background_tasks: BackgroundTasks, http_request: Request
):
    connector_name = request.connector.lower()

    if "infor" in connector_name:
        if request.order_type is None or request.order_number is None:
            raise HTTPException(422, "Infor requires an order type and order number.")
        rule = request.rule or "Default Rule"
        tenant = infor_setting("INFOR_TENANT")
        raw_data = await fetch_order_lines(
            request.order_type, request.order_number, http_request
        )
        documents = map_infor_response(
            raw_data,
            request.order_type,
            tenant,
            request.order_number,
        )
        documents = [apply_selected_rules(document, rule) for document in documents]
        OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        output_name = f"infor_{request.order_type}_{request.order_number}.json"
        (OUTPUT_FOLDER / output_name).write_text(
            json.dumps(documents, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        message = (
            f"Saved {len(documents)} Infor order line(s) to local JSON: {output_name}"
        )
        add_history_entry(
            connector=request.connector,
            mapper=request.mapper or "",
            rules=rule,
            outputs="Local JSON",
            status="completed",
            processed=len(documents),
            message=message,
        )
        return {
            "status": "success",
            "processed": len(documents),
            "rule": rule,
            "message": message,
        }

    if "jira" in connector_name:
        # Start a background polling task for Jira
        background_tasks.add_task(
            poll_jira,
            request.rule or "Default Rule",
            request.outputs,
        )
        add_history_entry(
            connector=request.connector,
            mapper=request.mapper or "",
            rules=request.rule or "Default Rule",
            outputs=request.outputs or "",
            status="polling",
            processed=0,
            message="Polling every 5 minutes.",
        )
        return {
            "status": "success",
            "processed": 0,
            "message": "Jira connector started. Polling every 5 minutes.",
            "rule": request.rule or "Default Rule",
        }

    if "sharepoint" in connector_name:
        result = await asyncio.to_thread(
            run_sharepoint_ingestion,
            request.rule or "Default Rule",
            request.outputs,
        )
        add_history_entry(
            connector=request.connector,
            mapper=request.mapper or "",
            rules=request.rule or "Default Rule",
            outputs=request.outputs or "",
            status="completed",
            processed=result["processed"],
        )
        return result

    # Default fallback for local files and other existing connector names.
    INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    raw_files = read_local_text_files(INPUT_FOLDER)
    canonical_documents = map_local_files_to_canonical(raw_files)
    processed_documents = []

    for document in canonical_documents:
        document = apply_selected_rules(document, request.rule or "Default Rule")
        processed_documents.append(document)
        output_name = Path(document["file_name"]).with_suffix(".json").name
        output_path = OUTPUT_FOLDER / output_name
        output_path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    publish_selected_outputs(processed_documents, request.outputs)

    add_history_entry(
        connector=request.connector,
        mapper=request.mapper or "",
        rules=request.rule or "Default Rule",
        outputs=request.outputs or "",
        status="completed",
        processed=len(canonical_documents),
    )

    return {
        "status": "success",
        "processed": len(processed_documents),
        "rule": request.rule or "Default Rule",
    }


# ---------------------------------------------------------------------------
# Config - Connectors
# ---------------------------------------------------------------------------


@app.get("/api/config/connectors")
def get_connectors():
    """Return all stored connectors."""
    return list_connectors()


@app.post("/api/config/connectors", status_code=201)
def create_connector(body: ConfigItemCreate):
    """Add a new connector. Returns the created item."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Connector name must not be empty.")
    try:
        return add_connector(name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.delete("/api/config/connectors/{item_id}", status_code=204)
def remove_connector(item_id: int):
    """Delete a connector by ID. Returns 404 if not found."""
    try:
        deleted = delete_connector(item_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Connector is used by a saved pipeline."
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Connector not found.")


# ---------------------------------------------------------------------------
# Config - Rules
# ---------------------------------------------------------------------------


@app.get("/api/config/rules")
def get_rules():
    """Return all stored rules."""
    return list_rules()


@app.post("/api/config/rules", status_code=201)
def create_rule(body: ConfigItemCreate):
    """Add a new rule. Returns the created item."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Rule name must not be empty.")
    try:
        return add_rule(name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.delete("/api/config/rules/{item_id}", status_code=204)
def remove_rule(item_id: int):
    """Delete a rule by ID. Returns 404 if not found."""
    try:
        deleted = delete_rule(item_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Rule is used by a saved pipeline."
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found.")


# ---------------------------------------------------------------------------
# Config - Output Targets
# ---------------------------------------------------------------------------


@app.get("/api/config/outputs")
def get_outputs():
    """Return all stored output targets."""
    return list_outputs()


@app.post("/api/config/outputs", status_code=201)
def create_output(body: ConfigItemCreate):
    """Add a new output target. Returns the created item."""
    name = body.name.strip()
    if not name:
        raise HTTPException(
            status_code=422, detail="Output target name must not be empty."
        )
    try:
        return add_output(name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.delete("/api/config/outputs/{item_id}", status_code=204)
def remove_output(item_id: int):
    """Delete an output target by ID. Returns 404 if not found."""
    try:
        deleted = delete_output(item_id)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Output target is used by a saved pipeline."
        ) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Output target not found.")


# ---------------------------------------------------------------------------
# Config - Pipelines
# ---------------------------------------------------------------------------


@app.get("/api/config/pipelines")
def get_pipelines():
    """List all pipelines in the database"""
    return list_pipelines()


@app.get("/api/config/pipelines/{pipeline_id}")
def get_pipeline_by_id(pipeline_id: int):
    """Retrieve a specific pipeline by its ID, returns 404 if not found."""
    pipeline = get_pipeline(pipeline_id)
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Pipeline not found.")
    return pipeline


@app.post("/api/config/pipelines", status_code=201)
def create_pipeline(body: PipelineSave):
    """Add a new pipeline"""
    try:
        return add_pipeline(
            body.name, body.connector_id, body.rule_ids, body.output_ids
        )
    except PipelineDuplicateNameError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/config/pipelines/{pipeline_id}")
def edit_pipeline(pipeline_id: int, body: PipelineSave):
    """Update an existing pipeline, returns 404 if the pipeline does not exist"""
    try:
        pipeline = update_pipeline(
            pipeline_id, body.name, body.connector_id, body.rule_ids, body.output_ids
        )
    except PipelineDuplicateNameError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if pipeline is None:
        raise HTTPException(status_code=404, detail="Pipeline not found.")
    return pipeline


@app.delete("/api/config/pipelines/{pipeline_id}", status_code=204)
def remove_pipeline(pipeline_id: int):
    """Delete a pipeline by its ID, returns 404 if the pipeline does not exist"""
    if not delete_pipeline(pipeline_id):
        raise HTTPException(status_code=404, detail="Pipeline not found.")


# ---------------------------------------------------------------------------
# Ingestion History
# ---------------------------------------------------------------------------


@app.get("/api/history")
def get_history():
    """Return all ingestion history entries, newest first."""
    return list_history()


@app.delete("/api/history/{entry_id}", status_code=204)
def remove_history_entry(entry_id: int):
    """Delete a history entry by ID."""
    if not delete_history_entry(entry_id):
        raise HTTPException(status_code=404, detail="History entry not found.")


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------


@app.post("/api/auth/register")
def register(payload: dict):
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")
    try:
        auth.register_user(username, password)
        token = auth.create_token(username)
        return {"status": "ok", "username": username, "token": token}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="username already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/auth/login")
def login(payload: dict):
    username = payload.get("username")
    password = payload.get("password")
    if not username or not password:
        raise HTTPException(status_code=400, detail="username and password required")

    if auth.verify_user(username, password):
        if not auth.is_admin(username):
            if auth.is_mfa_enabled(username):
                tmp = auth.create_token_with_type(username, ttl=300, token_type="mfa")
                return {"mfa_required": True, "tmp_token": tmp}
            token = auth.create_token_with_type(
                username, ttl=3600, token_type="session"
            )
            return {"authenticated": True, "username": username, "token": token}
        token = auth.create_token_with_type(username, ttl=3600, token_type="session")
        return {"authenticated": True, "username": username, "token": token}
    raise HTTPException(status_code=401, detail="invalid credentials")


@app.post("/api/auth/verify")
def verify_token(payload: dict):
    token = payload.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    username = auth.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    return {"username": username}


@app.post("/api/auth/mfa/setup")
def mfa_setup(payload: dict):
    token = payload.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    username = auth.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    secret = auth.generate_mfa_secret()
    auth.set_mfa_secret(username, secret)
    issuer = "Fortude"
    otpauth = auth.generate_otpauth_url(secret, username, issuer)
    return {"secret": secret, "otpauth_url": otpauth}


@app.post("/api/auth/mfa/verify")
def mfa_verify(payload: dict):
    token = payload.get("token")
    code = payload.get("code")
    if not token or not code:
        raise HTTPException(status_code=400, detail="token and code required")
    username = auth.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="invalid or expired token")

    secret = auth.get_mfa_secret(username)
    if not secret:
        raise HTTPException(status_code=400, detail="mfa not setup")

    if not auth.verify_totp(secret, str(code)):
        raise HTTPException(status_code=401, detail="invalid mfa code")

    auth.enable_mfa(username)
    return {"status": "ok"}


@app.post("/api/auth/mfa/login")
def mfa_login(payload: dict):
    tmp_token = payload.get("tmp_token")
    code = payload.get("code")
    if not tmp_token or not code:
        raise HTTPException(status_code=400, detail="tmp_token and code required")

    username = auth.verify_token_with_type(tmp_token, expected_type="mfa")
    if not username:
        raise HTTPException(status_code=401, detail="invalid or expired mfa token")

    secret = auth.get_mfa_secret(username)
    if not secret:
        raise HTTPException(status_code=400, detail="mfa not setup")

    if not auth.verify_totp(secret, str(code)):
        raise HTTPException(status_code=401, detail="invalid mfa code")

    auth.delete_token(tmp_token)
    token = auth.create_token_with_type(username, ttl=3600, token_type="session")
    return {"authenticated": True, "username": username, "token": token}


@app.post("/api/auth/change")
def change_user(payload: dict):
    token = payload.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="token required")
    username = auth.verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="invalid or expired token")
    old_password = payload.get("old_password")
    if not old_password:
        raise HTTPException(status_code=400, detail="old_password required")

    if not auth.verify_user(username, old_password):
        raise HTTPException(status_code=401, detail="invalid current password")

    new_username = payload.get("new_username")
    new_password = payload.get("new_password")

    if not new_username and not new_password:
        raise HTTPException(
            status_code=400, detail="new_username or new_password required"
        )

    try:
        auth.update_user(username, new_username=new_username, new_password=new_password)
        return {"status": "ok", "username": new_username or username}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="username already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mongodb/ingest")
async def ingest_documents(request: IngestRequest):
    """
    Persist a batch of canonical documents for a registered source.

    The frontend must send documents in the same shape the source
    registry expects. Use `source: "jira"` for Jira tickets, and any
    other key present in SOURCES for other sources.
    """
    if request.source not in SOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown source '{request.source}'. "
            f"Valid sources: {list(SOURCES.keys())}",
        )

    summary = await persist(request.source, request.documents)
    return IngestResponse(**summary)
