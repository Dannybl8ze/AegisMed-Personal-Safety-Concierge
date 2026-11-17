"""AegisMed caregiver dashboard API (FastAPI).

Run locally from the ``aegismed-agent`` directory::

    python -m dashboard_api.main
"""
import asyncio
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import Runner
from google.genai import types

from app.agent import LLM_REVIEWER_NAME, app as adk_app
from app.config import gemini_mode
from app.extraction import extract_patient_id, parse_medication_text
from app.safety_rules import REVIEW_REQUIRED, canonical_patient_id
from app.security import redact_pii
from app.storage import Storage, StorageNotConfigured, get_storage
from dashboard_api import auth
from dashboard_api.session_service import StorageSessionService, session_key

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AegisMed Caregiver Safety Portal")

# Sessions live in the storage module, so any instance can resume a paused workflow.
runner = Runner(app=adk_app, session_service=StorageSessionService(), auto_create_session=True)

PAUSED_RESPONSE = "🚨 WARNING: Clinical safety check failed. Prescription request held pending caregiver override."
SECURITY_PAUSED_RESPONSE = (
    "🚨 SECURITY WARNING: Prompt-injection attempt detected. Prescription request held pending caregiver review."
)
REVIEW_PAUSED_RESPONSE = (
    "🚨 REVIEW NEEDED: This request could not be fully checked automatically. "
    "It is held pending caregiver review."
)
CAREGIVER_OUTCOMES = {"approved_by_caregiver": "approved", "rejected_by_caregiver": "rejected"}

# Abuse limits for the endpoint that calls Gemini. Both can be tuned per deployment.
CHAT_WINDOW_SECONDS = 5 * 60
DEFAULT_CHAT_LIMIT = 20  # requests per client per window
DEFAULT_DAILY_CHAT_LIMIT = 500  # requests per day for the whole deployment


# -------------------------------------------------------------
# Helpers
# -------------------------------------------------------------

def _error(status_code: int, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"status": "error", "message": message, **extra})


def _agent_error_message() -> str:
    if gemini_mode() == "unconfigured":
        return (
            "Gemini is not configured. Set GOOGLE_API_KEY, or GOOGLE_GENAI_USE_VERTEXAI=true "
            "with GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_LOCATION."
        )
    return "The safety workflow could not complete. See the server logs for details."


def _chat_message(sender: str, text: str, session_id: str, patient_id: str, status: Optional[str] = None) -> dict:
    message = {"sender": sender, "text": text}
    if sender == "agent":
        message["status"] = status
    message.update(
        session_id=session_id,
        patient_id=patient_id,
        timestamp=datetime.now().strftime("%H:%M"),
        ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return message


def _split_alerts(alerts: dict) -> tuple[list, list]:
    pending = [a for a in alerts.values() if a["status"] == "pending"]
    resolved = [a for a in alerts.values() if a["status"] != "pending"]
    return pending, resolved


def extract_referenced_patient(message: str, patients: dict) -> str:
    """Which patient a message refers to: explicit id first, then full name, then a name part."""
    text = message.lower()

    def mentions(term: str) -> bool:
        return bool(term) and re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", text) is not None

    for pid in patients:
        if mentions(pid) or mentions(pid.replace("patient-", "", 1)):
            return pid
    for pid, patient in patients.items():
        if mentions(patient.get("name", "")):
            return pid
    for pid, patient in patients.items():
        if any(len(part) > 2 and mentions(part) for part in patient.get("name", "").split()):
            return pid
    return "unknown"


def resolve_patient(text: str, patients: dict, selected: str) -> str:
    """The patient a request is about, as the id without its "patient-" prefix.

    An id written in the text wins, then a patient's name, then the patient chosen
    in the switcher. "unknown" means none of them applied.
    """
    explicit = extract_patient_id(text)
    if explicit != "unknown":
        return explicit
    named = extract_referenced_patient(text, patients)
    if named != "unknown":
        return named.replace("patient-", "", 1)
    chosen = canonical_patient_id(selected)
    return chosen.replace("patient-", "", 1) if chosen in patients else "unknown"


def build_agent_input(text: str, patients: dict, selected: str) -> str:
    """The workflow's input: the request already parsed, with the patient resolved.

    Parsing here means a request that names its patient only by name still gets
    the allergy check. A message that is already a JSON request is passed on as is.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            json.loads(stripped)
            return text
        except ValueError:
            pass
    request_fields = parse_medication_text(text)
    request_fields["patient_id"] = resolve_patient(text, patients, selected)
    return json.dumps(request_fields)


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def chat_limit_message(storage: Storage, client: str) -> Optional[str]:
    """A reason to refuse this chat request, or None when it is within the limits."""
    if storage.hit(f"chat:{client}", CHAT_WINDOW_SECONDS) > _int_env("AEGISMED_CHAT_LIMIT", DEFAULT_CHAT_LIMIT):
        return "Too many requests. Please wait a few minutes before sending another."
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if storage.hit(f"chat-day:{today}", 24 * 60 * 60) > _int_env("AEGISMED_DAILY_CHAT_LIMIT", DEFAULT_DAILY_CHAT_LIMIT):
        return "The daily request limit for this demo has been reached. Please try again tomorrow."
    return None


async def run_agent_message(user_id: str, session_id: str, message: str, resume_inputs: Optional[dict] = None) -> dict:
    """Run (or resume) the workflow for one session and summarise the outcome."""
    logger.info("Running agent for session %s (resume=%s)", session_id, resume_inputs is not None)
    storage = get_storage()
    key = session_key(adk_app.name, user_id, session_id)

    if resume_inputs:
        parts = [
            types.Part(
                function_response=types.FunctionResponse(
                    id=interrupt_id,
                    name="adk_request_input",
                    response=value if isinstance(value, dict) else {"response": value},
                )
            )
            for interrupt_id, value in resume_inputs.items()
        ]
        new_message = types.Content(role="user", parts=parts)
    else:
        new_message = types.Content(role="user", parts=[types.Part.from_text(text=message)])

    # Snapshot a paused session so a failed resume can be retried from the same point.
    snapshot = await asyncio.to_thread(storage.get_session, key) if resume_inputs else None

    texts = []
    final_output = None
    interrupt_id = None
    try:
        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=new_message):
            if event.output is not None:
                final_output = event.output
            if not (event.content and event.content.parts):
                continue
            for part in event.content.parts:
                # The reviewer's raw JSON is for the rule node, not for the chat reply.
                if part.text and event.author != LLM_REVIEWER_NAME:
                    texts.append(part.text)
                if part.function_call and part.function_call.name == "adk_request_input":
                    interrupt_id = part.function_call.id
    except Exception:
        logger.error("Agent workflow failed for session %s", session_id, exc_info=True)
        if snapshot is not None:
            await asyncio.to_thread(storage.save_session, key, snapshot)
        else:
            await asyncio.to_thread(storage.delete_session, key)
        return {"status": "error", "session_id": session_id, "message": _agent_error_message()}

    session = await runner.session_service.get_session(app_name=adk_app.name, user_id=user_id, session_id=session_id)
    state = session.state if session else {}
    req = state.get("medication_request") or {}

    if interrupt_id:
        risk = state.get("risk_assessment") or {}
        alert = {
            "session_id": session_id,
            "user_id": user_id,
            "patient_id": req.get("patient_id", "unknown"),
            "drug_name": req.get("drug_name", "unknown"),
            "dose_mg": req.get("dose_mg", 0.0),
            "frequency_per_day": req.get("frequency_per_day", 1),
            "safety_result": state.get("mcp_safety_result", ""),
            "risk_level": risk.get("risk_level", "High"),
            "warnings": risk.get("warnings", []),
            "explanation": risk.get("explanation", ""),
            "interrupt_id": interrupt_id,
            "status": "pending",
        }
        await asyncio.to_thread(storage.save_alert, session_id, alert)
        if state.get("security_event"):
            paused_response = SECURITY_PAUSED_RESPONSE
        elif str(state.get("mcp_safety_result", "")).startswith(REVIEW_REQUIRED):
            paused_response = REVIEW_PAUSED_RESPONSE
        else:
            paused_response = PAUSED_RESPONSE
        return {
            "status": "paused",
            "session_id": session_id,
            "interrupt_id": interrupt_id,
            "response": paused_response,
            "patient_id": req.get("patient_id", "unknown"),
            "state": state,
        }

    # The workflow finished, so its session is no longer needed.
    await asyncio.to_thread(storage.delete_session, key)
    return {
        "status": "completed",
        "session_id": session_id,
        "response": "\n".join(texts) if texts else "Request processed.",
        "patient_id": req.get("patient_id", "unknown"),
        "output": final_output,
        "state": state,
    }


# -------------------------------------------------------------
# Error handling: always answer with JSON
# -------------------------------------------------------------

@app.exception_handler(StorageNotConfigured)
async def storage_not_configured(request: Request, exc: StorageNotConfigured) -> JSONResponse:
    return _error(503, str(exc))


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s", request.url.path, exc_info=exc)
    return _error(500, "Internal server error.")


# -------------------------------------------------------------
# Access control
# -------------------------------------------------------------

@app.middleware("http")
async def require_sign_in(request: Request, call_next):
    """Every data endpoint needs a session; only login, logout and session checks are open."""
    path = request.url.path
    if path.startswith("/api/") and path not in auth.PUBLIC_API_PATHS and auth.auth_required():
        if not auth.access_code():
            return _error(503, "Access is not configured. Set AEGISMED_ACCESS_CODE for this deployment.")
        if not auth.is_signed_in(request):
            return _error(401, "Sign in required.")
    return await call_next(request)


@app.get("/api/session", response_class=JSONResponse)
def get_session(request: Request):
    """Whether sign-in is required and whether this browser is signed in."""
    required = auth.auth_required()
    return {
        "required": required,
        "authenticated": (not required) or auth.is_signed_in(request),
        "configured": bool(auth.access_code()) or not auth.is_hosted(),
    }


@app.post("/api/login", response_class=JSONResponse)
async def post_login(request: Request, code: str = Form("")):
    expected = auth.access_code()
    if not expected:
        if auth.is_hosted():
            return _error(503, "Access is not configured. Set AEGISMED_ACCESS_CODE for this deployment.")
        return {"status": "success", "required": False}

    attempts = await asyncio.to_thread(
        get_storage().hit, f"login:{auth.client_id(request)}", auth.LOGIN_WINDOW_SECONDS
    )
    if attempts > auth.LOGIN_ATTEMPTS:
        response = _error(429, "Too many sign-in attempts. Please wait 15 minutes and try again.")
        response.headers["Retry-After"] = str(auth.LOGIN_WINDOW_SECONDS)
        return response
    if not auth.code_matches(code, expected):
        return _error(401, "That access code is not correct.")

    response = JSONResponse({"status": "success"})
    auth.set_session_cookie(response, request, expected)
    return response


@app.post("/api/logout", response_class=JSONResponse)
def post_logout():
    response = JSONResponse({"status": "success"})
    auth.clear_session_cookie(response)
    return response


# -------------------------------------------------------------
# HTTP endpoints
# -------------------------------------------------------------

@app.get("/api/state", response_class=JSONResponse)
def get_state():
    """Everything the dashboard renders, in one response."""
    storage = get_storage()
    pending, resolved = _split_alerts(storage.get_alerts())
    return {
        "patients": storage.get_patients(),
        "history": storage.get_chat(),
        "pending": pending,
        "resolved": resolved,
    }


@app.get("/api/pending", response_class=JSONResponse)
def get_pending():
    pending, _ = _split_alerts(get_storage().get_alerts())
    return pending


@app.post("/api/patients/add", response_class=JSONResponse)
def add_patient(
    patient_id: str = Form(...),
    name: str = Form(...),
    age: int = Form(...),
    allergies: str = Form(""),
    active: str = Form(...),
    avatar: str = Form("👨"),
):
    pid = canonical_patient_id(patient_id)
    patient = {
        "name": name.strip(),
        "age": age,
        "allergies": [a.strip().lower() for a in allergies.split(",") if a.strip()],
        "active": active.strip(),
        "avatar": avatar.strip(),
    }
    get_storage().save_patient(pid, patient)
    return {"status": "success", "patient_id": pid, "patient": patient}


@app.post("/api/chat", response_class=JSONResponse)
async def post_chat(
    request: Request,
    message: str = Form(...),
    session_id: str = Form("session-default"),
    user_id: str = Form("user-default"),
    patient_id: str = Form("unknown"),
):
    storage = get_storage()
    refusal = await asyncio.to_thread(chat_limit_message, storage, auth.client_id(request))
    if refusal:
        response = _error(429, refusal)
        response.headers["Retry-After"] = str(CHAT_WINDOW_SECONDS)
        return response

    # Scrub PII at the boundary so it is never stored or sent onward in the clear.
    safe_message, _ = redact_pii(message)

    patients = await asyncio.to_thread(storage.get_patients)
    target_pid = patient_id.strip().lower()
    if target_pid in ("all", "unknown"):
        target_pid = extract_referenced_patient(safe_message, patients)
    user_msg = _chat_message("user", safe_message, session_id, target_pid)

    result = await run_agent_message(user_id, session_id, build_agent_input(safe_message, patients, patient_id))
    if result["status"] == "error":
        return JSONResponse(status_code=502, content=result)

    agent_pid = canonical_patient_id(result.get("patient_id", "unknown"))
    if agent_pid != "unknown":
        target_pid = agent_pid
        user_msg["patient_id"] = target_pid

    agent_msg = _chat_message("agent", result["response"], session_id, target_pid, status=result.get("status"))
    await asyncio.to_thread(storage.append_chat, user_msg, agent_msg)
    return result


@app.post("/api/resolve", response_class=JSONResponse)
async def post_resolve(session_id: str = Form(...), decision: str = Form(...)):
    storage = get_storage()
    alert = await asyncio.to_thread(storage.get_alert, session_id)
    if not alert:
        return JSONResponse(status_code=404, content={"message": "Session not found"})
    if alert["status"] != "pending":
        return JSONResponse(status_code=409, content={"message": "Alert already resolved", "status": alert["status"]})

    result = await run_agent_message(
        alert["user_id"], session_id, message="", resume_inputs={alert["interrupt_id"]: decision}
    )
    if result["status"] == "error":
        return JSONResponse(status_code=502, content=result)
    if result["status"] == "paused":
        return result

    # Record what the workflow actually decided, not what was requested.
    outcome = CAREGIVER_OUTCOMES.get((result.get("output") or {}).get("status"))
    if not outcome:
        logger.error("Resume of session %s finished without a caregiver outcome", session_id)
        return _error(502, "The workflow resumed but did not report a caregiver decision.", session_id=session_id)

    alert["status"] = outcome
    await asyncio.to_thread(storage.save_alert, session_id, alert)

    pid = canonical_patient_id(alert.get("patient_id", "unknown"))
    await asyncio.to_thread(
        storage.append_chat,
        _chat_message("caregiver", f"Caregiver decision: {decision.upper()}", session_id, pid),
        _chat_message("agent", result["response"], session_id, pid, status=result.get("status")),
    )
    return result


@app.post("/api/reset", response_class=JSONResponse)
def post_reset():
    get_storage().reset_demo_state()
    return {"message": "System logs and agent runner reset successfully."}


# -------------------------------------------------------------
# Static UI (container deployments only)
# -------------------------------------------------------------

def mount_static_ui(application: FastAPI, directory: Path) -> bool:
    """Serve the exported dashboard from ``directory`` at "/", if it exists.

    On Vercel the Next.js service serves the UI, so nothing is mounted there.
    The Docker image builds the UI to static files and serves them from here.
    Call this after every API route is registered so the API keeps priority.
    """
    if not directory.is_dir():
        return False
    application.mount("/", StaticFiles(directory=directory, html=True), name="web")
    return True


mount_static_ui(app, Path(os.environ.get("AEGISMED_WEB_DIST") or Path(__file__).resolve().parents[1] / "web_dist"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "dashboard_api.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
