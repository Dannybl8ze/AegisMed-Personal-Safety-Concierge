"""AegisMed caregiver dashboard API (FastAPI).

Run locally from the ``aegismed-agent`` directory::

    python -m dashboard_api.main
"""
import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse
from google.adk.runners import Runner
from google.genai import types

from app.agent import LLM_REVIEWER_NAME, app as adk_app
from app.config import gemini_mode
from app.safety_rules import canonical_patient_id
from app.security import redact_pii
from app.storage import StorageNotConfigured, get_storage
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
CAREGIVER_OUTCOMES = {"approved_by_caregiver": "approved", "rejected_by_caregiver": "rejected"}


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
        return {
            "status": "paused",
            "session_id": session_id,
            "interrupt_id": interrupt_id,
            "response": SECURITY_PAUSED_RESPONSE if state.get("security_event") else PAUSED_RESPONSE,
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
    message: str = Form(...),
    session_id: str = Form("session-default"),
    user_id: str = Form("user-default"),
    patient_id: str = Form("unknown"),
):
    storage = get_storage()
    # Scrub PII at the boundary so it is never stored or sent onward in the clear.
    safe_message, _ = redact_pii(message)

    target_pid = patient_id.strip().lower()
    if target_pid in ("all", "unknown"):
        target_pid = extract_referenced_patient(safe_message, await asyncio.to_thread(storage.get_patients))
    user_msg = _chat_message("user", safe_message, session_id, target_pid)

    result = await run_agent_message(user_id, session_id, safe_message)
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "dashboard_api.main:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", 8000)),
        reload=False,
    )
