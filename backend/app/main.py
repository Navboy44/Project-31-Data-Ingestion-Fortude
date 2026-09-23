import json
import asyncio
from contextlib import asynccontextmanager
import logging
import threading
from pathlib import Path
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from connectors.local_folder_connector import read_local_text_files
from mappers.local_file_mapper import map_local_files_to_canonical
from connectors.sharepoint_connector import (
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
import sys
sys.path.append('.')
from connectors.Jira_API_connector import get_my_issues,get_jira_fields
from mappers.jira_mapper import map_jira_response_to_canonical
from mappers.jira_transformer import transform_canonical_tickets_for_l3
from outputs.kafka_output import publish_documents as publish_kafka_documents
from outputs.qdrant_output import publish_documents as publish_qdrant_documents
import sqlite3

BASE_FOLDER = Path(__file__).resolve().parents[2]
OUTPUT_FOLDER = BASE_FOLDER / "local_data" / "output"
INPUT_FOLDER = BASE_FOLDER / "local_data" / "input"  # ADD THIS LINE

# BASE_FOLDER = Path(__file__).resolve().parents[2]
# OUTPUT_FOLDER = BASE_FOLDER / "local_data" / "output"
POLL_INTERVAL_SECONDS = 300
SHAREPOINT_POLL_RULE = "Knowledge Base Rules"

logger = logging.getLogger(__name__)
ingestion_lock = threading.Lock()
polling_task = None


# ---------------------------------------------------------------------------
# Lifespan — initialise databases once on startup
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global polling_task
    auth.init_db()
    init_config_db()
    polling_task = asyncio.create_task(poll_sharepoint_ingestion())
    try:
        yield
    finally:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        polling_task = None


app = FastAPI(lifespan=lifespan)

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
    while True:
        print(f"Polling Jira... (using rule: {rule})")
        try:
            # 1. Fetch raw data from Jira directly (no FastAPI wrapper)
            jira_data = await get_my_issues()
            print(jira_data)
            print(f"DEBUG: Jira API returned {jira_data.get('total')} tickets.")
            # 2. Map to canonical schema
            canonical_tickets = map_jira_response_to_canonical(jira_data)
            print(f"DEBUG: Mapper successfully processed {len(canonical_tickets)} tickets.")
            # 3. Apply rules / transformations based on user selection
            if "L3" in (rule or ""):
                final_tickets = transform_canonical_tickets_for_l3(canonical_tickets)
            else:
                final_tickets = canonical_tickets

            publish_selected_outputs(final_tickets, selected_outputs)
                
            # 4. Save output to jira_issues.json
            OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
            output_file = OUTPUT_FOLDER / "jira_issues.json"
            
            existing_tickets = []
            if output_file.exists():
                try:
                    existing_tickets = json.loads(output_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    pass
            
            # Deduplicate by ticket_key
            ticket_dict = {t.get("ticket_key"): t for t in existing_tickets if isinstance(t, dict) and t.get("ticket_key")}
            
            for t in final_tickets:
                key = t.get("ticket_key")
                if key:
                    ticket_dict[key] = t
                    
            merged_tickets = list(ticket_dict.values())
            
            output_file.write_text(
                json.dumps(merged_tickets, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            print(f"Successfully appended/updated Jira tickets in {output_file.name}. Total tickets: {len(merged_tickets)}")
            
        except Exception as e:
            print(f"Error polling Jira: {e}")
            
        await asyncio.sleep(300)

@app.post("/api/ingest/local-folder")
async def ingest_local_folder(request: IngestionRequest, background_tasks: BackgroundTasks):
    connector_name = request.connector.lower()

    if "infor" in connector_name:
        raise HTTPException(
            status_code=501,
            detail="Connector 'Infor Sales' is not completed yet."
        )

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
# Config — Connectors
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
    if not delete_connector(item_id):
        raise HTTPException(status_code=404, detail="Connector not found.")


# ---------------------------------------------------------------------------
# Config — Rules
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
    if not delete_rule(item_id):
        raise HTTPException(status_code=404, detail="Rule not found.")


# ---------------------------------------------------------------------------
# Config — Output Targets
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
        raise HTTPException(status_code=422, detail="Output target name must not be empty.")
    try:
        return add_output(name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@app.delete("/api/config/outputs/{item_id}", status_code=204)
def remove_output(item_id: int):
    """Delete an output target by ID. Returns 404 if not found."""
    if not delete_output(item_id):
        raise HTTPException(status_code=404, detail="Output target not found.")


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
            token = auth.create_token_with_type(username, ttl=3600, token_type="session")
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
        raise HTTPException(status_code=400, detail="new_username or new_password required")

    try:
        auth.update_user(username, new_username=new_username, new_password=new_password)
        return {"status": "ok", "username": new_username or username}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="username already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
