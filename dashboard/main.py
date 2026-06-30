import os
import json
import logging
import asyncio
from typing import Any, Optional
from datetime import datetime
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from google.adk.apps import App
from google.adk.runners import InMemoryRunner
from google.genai import types

# Import the AegisMed ADK App
import sys
agent_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aegismed-agent")
if agent_dir not in sys.path:
    sys.path.insert(0, agent_dir)
from app.agent import app as adk_app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI App
app = FastAPI(title="AegisMed Caregiver Safety Portal")

# Setup templates and static directories
templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
os.makedirs(templates_dir, exist_ok=True)
templates = Jinja2Templates(directory=templates_dir)

# File to persist pending caregiver alerts
PENDING_SESSIONS_FILE = "pending_sessions.json"
CHAT_HISTORY_FILE = "chat_history.json"

# In-memory runner for dev execution
runner = InMemoryRunner(app=adk_app)
runner.auto_create_session = True

def get_pending_sessions() -> dict:
    if os.path.exists(PENDING_SESSIONS_FILE):
        try:
            with open(PENDING_SESSIONS_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_pending_sessions(sessions: dict):
    with open(PENDING_SESSIONS_FILE, 'w') as f:
        json.dump(sessions, f, indent=2)

def get_chat_history() -> list:
    if os.path.exists(CHAT_HISTORY_FILE):
        try:
            with open(CHAT_HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_chat_history(history: list):
    with open(CHAT_HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)

PATIENTS_FILE = "patients.json"

def get_patients_db() -> dict:
    if os.path.exists(PATIENTS_FILE):
        try:
            with open(PATIENTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "patient-101": {"name": "John Doe", "age": 62, "allergies": ["sulfa", "sulfonamide", "bactrim"], "active": "Lisinopril 10mg", "avatar": "👨‍🦳"},
        "patient-102": {"name": "Jane Smith", "age": 45, "allergies": ["penicillin", "amoxicillin", "ampicillin"], "active": "Atorvastatin 20mg", "avatar": "👩"},
        "patient-103": {"name": "Robert Johnson", "age": 71, "allergies": ["aspirin", "acetylsalicylic acid"], "active": "Metoprolol 50mg", "avatar": "👴"},
        "patient-104": {"name": "Alice Brown", "age": 29, "allergies": [], "active": "None", "avatar": "👩‍🦰"}
    }

def save_patients_db(patients: dict):
    with open(PATIENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(patients, f, indent=2)

# Helper function to run the agent
async def run_agent_message(user_id: str, session_id: str, message: str, resume_inputs: Optional[dict] = None) -> dict:
    logger.info(f"Running agent for session {session_id} (resume={resume_inputs is not None})")
    
    # Run the agent asynchronously
    events = []
    final_output = None
    interrupted = False
    interrupt_id = None
    
    if resume_inputs:
        parts = []
        for int_id, val in resume_inputs.items():
            response_payload = val if isinstance(val, dict) else {"response": val}
            parts.append(
                types.Part(
                    function_response=types.FunctionResponse(
                        id=int_id,
                        name="adk_request_input",
                        response=response_payload
                    )
                )
            )
        new_msg_content = types.Content(role="user", parts=parts)
    elif message:
        new_msg_content = types.Content(role="user", parts=[types.Part.from_text(text=message)])
    else:
        new_msg_content = None
        
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=new_msg_content
        ):
            # Capture UI/model events
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        events.append(part.text)
            
            # Capture final output
            if event.output is not None:
                final_output = event.output
            
            # Capture interruption
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call and part.function_call.name == "adk_request_input":
                        interrupted = True
                        interrupt_id = part.function_call.id
                
    except Exception as e:
        logger.error(f"Error executing agent workflow: {e}", exc_info=True)
        return {"status": "error", "message": f"Execution error: {e}"}

    # Fetch session state to check mcp check and risk assessment
    session = await runner.session_service.get_session(app_name="app", user_id=user_id, session_id=session_id)
    state = session.state if session else {}
    
    response_text = "\n".join(events) if events else "Request processed."
    
    if interrupted and interrupt_id:
        req = state.get("medication_request", {})
        safety_result = state.get("mcp_safety_result", "Dosage threshold limits exceeded.")
        risk = state.get("risk_assessment", {})
        
        # Save to pending sessions file for caregiver view
        sessions = get_pending_sessions()
        sessions[session_id] = {
            "session_id": session_id,
            "user_id": user_id,
            "patient_id": req.get("patient_id", "unknown"),
            "drug_name": req.get("drug_name", "unknown"),
            "dose_mg": req.get("dose_mg", 0.0),
            "frequency_per_day": req.get("frequency_per_day", 1),
            "safety_result": safety_result,
            "risk_level": risk.get("risk_level", "High"),
            "warnings": risk.get("warnings", []),
            "explanation": risk.get("explanation", ""),
            "interrupt_id": interrupt_id,
            "status": "pending"
        }
        save_pending_sessions(sessions)
        
        response_text = "🚨 WARNING: Clinical safety check failed. Prescription request held pending caregiver override."
        return {
            "status": "paused",
            "session_id": session_id,
            "interrupt_id": interrupt_id,
            "response": response_text,
            "patient_id": req.get("patient_id", "unknown"),
            "state": state
        }
    
    req = state.get("medication_request") or {}
    return {
        "status": "completed",
        "session_id": session_id,
        "response": response_text,
        "patient_id": req.get("patient_id", "unknown"),
        "output": final_output,
        "state": state
    }

# -------------------------------------------------------------
# 3. HTTP Endpoints
# -------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    sessions = get_pending_sessions()
    history = get_chat_history()
    patients = get_patients_db()
    pending_list = [s for s in sessions.values() if s["status"] == "pending"]
    resolved_list = [s for s in sessions.values() if s["status"] != "pending"]
    
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "pending": pending_list,
            "resolved": resolved_list,
            "history": history,
            "patients": patients
        }
    )

@app.post("/api/patients/add", response_class=JSONResponse)
async def add_patient(
    patient_id: str = Form(...),
    name: str = Form(...),
    age: int = Form(...),
    allergies: str = Form(""),
    active: str = Form(...),
    avatar: str = Form("👨")
):
    patients = get_patients_db()
    pid_clean = patient_id.strip().lower()
    if not pid_clean.startswith("patient-"):
        pid_clean = f"patient-{pid_clean}"
        
    allergies_list = [a.strip().lower() for a in allergies.split(",") if a.strip()]
    
    patients[pid_clean] = {
        "name": name.strip(),
        "age": age,
        "allergies": allergies_list,
        "active": active.strip(),
        "avatar": avatar.strip()
    }
    
    save_patients_db(patients)
    return JSONResponse(content={"status": "success", "patient_id": pid_clean, "patient": patients[pid_clean]})

@app.get("/api/pending", response_class=JSONResponse)
async def get_pending_api():
    sessions = get_pending_sessions()
    pending_list = [s for s in sessions.values() if s["status"] == "pending"]
    return JSONResponse(content=pending_list)

def extract_referenced_patient(message: str, patients: dict) -> str:
    msg_lower = message.lower()
    for pid, p in patients.items():
        if pid.lower() in msg_lower or pid.replace("patient-", "").lower() in msg_lower:
            return pid
        name = p.get("name", "")
        if name and name.lower() in msg_lower:
            return pid
        name_parts = name.split(" ")
        for part in name_parts:
            if len(part) > 2 and part.lower() in msg_lower:
                return pid
    return "unknown"

@app.post("/api/chat", response_class=JSONResponse)
async def post_chat(
    message: str = Form(...),
    session_id: str = Form("session-default"),
    user_id: str = Form("user-default"),
    patient_id: str = Form("unknown")
):
    history = get_chat_history()
    timestamp = datetime.now().strftime("%H:%M")
    
    target_pid = patient_id.strip().lower()
    if target_pid == "all" or target_pid == "unknown":
        target_pid = extract_referenced_patient(message, get_patients_db())
        
    user_msg = {
        "sender": "user",
        "text": message,
        "session_id": session_id,
        "patient_id": target_pid,
        "timestamp": timestamp
    }
    history.append(user_msg)
    
    result = await run_agent_message(user_id, session_id, message)
    
    agent_pid = result.get("patient_id", "unknown")
    if agent_pid != "unknown":
        if not agent_pid.strip().lower().startswith("patient-"):
            agent_pid = f"patient-{agent_pid.strip().lower()}"
        target_pid = agent_pid
        user_msg["patient_id"] = target_pid
        
    history.append({
        "sender": "agent",
        "text": result["response"],
        "status": result.get("status"),
        "session_id": session_id,
        "patient_id": target_pid,
        "timestamp": datetime.now().strftime("%H:%M")
    })
    save_chat_history(history)
    
    return JSONResponse(content=result)
 
@app.post("/api/resolve", response_class=JSONResponse)
async def post_resolve(session_id: str = Form(...), decision: str = Form(...)):
    sessions = get_pending_sessions()
    if session_id not in sessions:
        return JSONResponse(status_code=404, content={"message": "Session not found"})
        
    session_data = sessions[session_id]
    interrupt_id = session_data["interrupt_id"]
    user_id = session_data["user_id"]
    patient_id = session_data.get("patient_id", "unknown")
    
    resume_inputs = {interrupt_id: decision}
    result = await run_agent_message(user_id, session_id, message="", resume_inputs=resume_inputs)
    
    session_data["status"] = "approved" if "approve" in decision else "rejected"
    sessions[session_id] = session_data
    save_pending_sessions(sessions)
    
    history = get_chat_history()
    timestamp = datetime.now().strftime("%H:%M")
    
    clean_pid = patient_id.strip().lower()
    if clean_pid != "unknown" and not clean_pid.startswith("patient-"):
        clean_pid = f"patient-{clean_pid}"
        
    history.append({
        "sender": "caregiver",
        "text": f"Caregiver decision: {decision.upper()}",
        "session_id": session_id,
        "patient_id": clean_pid,
        "timestamp": timestamp
    })
    history.append({
        "sender": "agent",
        "text": result["response"],
        "status": result.get("status"),
        "session_id": session_id,
        "patient_id": clean_pid,
        "timestamp": datetime.now().strftime("%H:%M")
    })
    save_chat_history(history)
    
    return JSONResponse(content=result)

@app.post("/api/reset", response_class=JSONResponse)
async def post_reset():
    if os.path.exists(PENDING_SESSIONS_FILE):
        os.remove(PENDING_SESSIONS_FILE)
    if os.path.exists(CHAT_HISTORY_FILE):
        os.remove(CHAT_HISTORY_FILE)
    global runner
    runner = InMemoryRunner(app=adk_app)
    runner.auto_create_session = True
    return JSONResponse(content={"message": "System logs and agent runner reset successfully."})

if __name__ == "__main__":
    import uvicorn
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host=host, port=port, reload=False)
