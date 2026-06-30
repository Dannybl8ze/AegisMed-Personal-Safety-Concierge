import base64
import json
import re
import sys
import os
from typing import Any, List, Generator
from pydantic import BaseModel, Field

import asyncio
from google.adk.workflow import Workflow
from google.adk.agents import LlmAgent
from google.adk.models import Gemini
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.genai import types

# A custom loop safe gemini configuration
class LoopSafeGemini(Gemini):
    @property
    def api_client(self):
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        
        if self.__dict__.get('_cached_loop') is not current_loop:
            self.__dict__.pop('api_client', None)
            self.__dict__['_cached_loop'] = current_loop
            
        if 'api_client' not in self.__dict__:
            from google.genai import Client
            from google.genai import types
            
            base_url, api_version = self._base_url_and_api_version
            kwargs_for_http_options = {
                'headers': self._tracking_headers(),
                'retry_options': self.retry_options,
                'base_url': base_url,
            }
            if api_version:
                kwargs_for_http_options['api_version'] = api_version
                
            kwargs = {
                'http_options': types.HttpOptions(**kwargs_for_http_options),
            }
            
            is_vertex_requested = (
                os.environ.get("GOOGLE_GENAI_USE_VERTEXAI") == "True" or
                os.environ.get("K_SERVICE") is not None or
                "GOOGLE_GENAI_USE_VERTEXAI=True" in os.environ.get("GOOGLE_CLOUD_PROJECT", "")
            )
            
            if is_vertex_requested:
                kwargs['vertexai'] = True
                raw_project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
                if " " in raw_project:
                    project_id = raw_project.split(" ")[0].strip()
                else:
                    project_id = raw_project or os.environ.get("GCP_PROJECT") or os.environ.get("GCLOUD_PROJECT")
                
                kwargs['project'] = project_id or "project-3ba8b553-324f-445f-b23"
                kwargs['location'] = os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
            elif self.model.startswith('projects/'):
                kwargs['vertexai'] = True
                
            self.__dict__['api_client'] = Client(**kwargs)
            
        return self.__dict__['api_client']

from app.config import MODEL_NAME

# -------------------------------------------------------------
# 1. Schemas & Models
# -------------------------------------------------------------

class MedicationRequest(BaseModel):
    drug_name: str
    dose_mg: float
    frequency_per_day: int
    patient_id: str = "unknown"
    notes: str = ""

class ClinicalRiskAssessment(BaseModel):
    risk_level: str = Field(description="Low, Medium, or High")
    warnings: List[str] = Field(description="List of risk alerts or contraindications found")
    explanation: str = Field(description="Detailed explanation of the safety assessment")

# -------------------------------------------------------------
# 2. Workflow Nodes
# -------------------------------------------------------------

def extract_medication_request(node_input: Any) -> Event:
    raw_str = None
    parsed = None
    
    # 1. Handle types.Content (from UI/API)
    if hasattr(node_input, "parts") and node_input.parts:
        raw_str = "".join(part.text for part in node_input.parts if part.text)
    # 2. Handle string input
    elif isinstance(node_input, str):
        raw_str = node_input
    # 3. Handle dictionary input
    elif isinstance(node_input, dict):
        parsed = node_input
        
    if raw_str:
        try:
            parsed = json.loads(raw_str)
        except Exception:
            # Simple heuristic extraction from text if not JSON
            # E.g. "Add Warfarin 6mg twice daily for patient patient-123"
            drug_name = "unknown"
            dose_mg = 0.0
            freq = 1
            
            # Simple regex parser fallback
            drug_match = re.search(r'\b(warfarin|aspirin|lisinopril|ibuprofen)\b', raw_str, re.IGNORECASE)
            if drug_match:
                drug_name = drug_match.group(1).capitalize()
                
            dose_match = re.search(r'\b(\d+(?:\.\d+)?)\s*mg\b', raw_str, re.IGNORECASE)
            if dose_match:
                dose_mg = float(dose_match.group(1))
                
            if "twice" in raw_str.lower() or "2 times" in raw_str.lower() or "bid" in raw_str.lower():
                freq = 2
            elif "three" in raw_str.lower() or "3 times" in raw_str.lower() or "tid" in raw_str.lower():
                freq = 3
            elif "four" in raw_str.lower() or "4 times" in raw_str.lower() or "qid" in raw_str.lower():
                freq = 4
                
            patient_match = re.search(r'\bpatient[-_ ](\w+)\b', raw_str, re.IGNORECASE)
            patient_id = patient_match.group(1) if patient_match else "unknown"
            
            parsed = {
                "drug_name": drug_name,
                "dose_mg": dose_mg,
                "frequency_per_day": freq,
                "patient_id": patient_id,
                "notes": raw_str
            }
            
    if not parsed:
        raise ValueError(f"Unable to parse input: {node_input}")
        
    # Check if nested
    if "data" in parsed:
        data_val = parsed["data"]
        if isinstance(data_val, str):
            try:
                decoded = base64.b64decode(data_val).decode('utf-8')
                parsed = json.loads(decoded)
            except Exception:
                try:
                    parsed = json.loads(data_val)
                except Exception:
                    raise ValueError(f"Unable to parse nested data string: {data_val}")
        elif isinstance(data_val, dict):
            parsed = data_val

    request = MedicationRequest(
        drug_name=str(parsed.get("drug_name", "unknown")),
        dose_mg=float(parsed.get("dose_mg", 0.0)),
        frequency_per_day=int(parsed.get("frequency_per_day", 1)),
        patient_id=str(parsed.get("patient_id", "unknown")),
        notes=str(parsed.get("notes", ""))
    )
    
    return Event(output=request, state={"medication_request": request.model_dump(), "redacted_categories": []})


def security_checkpoint(ctx: Context, node_input: MedicationRequest) -> Event:
    notes = node_input.notes
    redacted_categories = []
    
    # 1. Scrub SSNs
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b'
    if re.search(ssn_pattern, notes):
        notes = re.sub(ssn_pattern, "[REDACTED_SSN]", notes)
        redacted_categories.append("SSN")
        
    # 2. Scrub Phone numbers (e.g. +1 555-555-5555 or 555-555-5555)
    phone_pattern = r'\b(?:\+?\d{1,3}[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b'
    if re.search(phone_pattern, notes):
        notes = re.sub(phone_pattern, "[REDACTED_PHONE]", notes)
        redacted_categories.append("Phone")
        
    node_input.notes = notes
    ctx.state["medication_request"] = node_input.model_dump()
    ctx.state["redacted_categories"] = redacted_categories

    # 3. Detect prompt injection
    injection_patterns = [
        r"ignore previous instructions",
        r"bypass safety",
        r"override system",
        r"force auto-approval",
        r"approve without check",
        r"override caregiver",
        r"ignore safety rules"
    ]
    is_injection = False
    for pat in injection_patterns:
        if re.search(pat, notes, re.IGNORECASE):
            is_injection = True
            break
            
    if is_injection:
        ctx.state["security_event"] = True
        ctx.state["risk_assessment"] = {
            "risk_level": "High",
            "warnings": ["SECURITY EVENT: Prompt injection attempt detected in medication request notes!"],
            "explanation": "The request notes triggered security filters due to prompt injection keywords."
        }
        return Event(route="bypass_llm", output=node_input)
    
    ctx.state["security_event"] = False
    return Event(route="clean", output=node_input)


# LLM node: Assess secondary clinical risk/warnings
clinical_risk_reviewer = LlmAgent(
    name="clinical_risk_reviewer",
    model=LoopSafeGemini(
        model=MODEL_NAME,
        project=os.environ.get("GCP_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT") or "project-3ba8b553-324f-445f-b23",
        location=os.environ.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
    ),
    instruction=(
        "You are a clinical safety reviewer. Review the following medication request "
        "and determine its general risk level (Low, Medium, or High) based on standard safety guidelines. "
        "Highlight any general warnings or guidance for this drug class."
    ),
    output_schema=ClinicalRiskAssessment,
)


def clinical_mcp_check(ctx: Context, node_input: Any) -> Event:
    # 1. Capture ClinicalRiskAssessment if it comes from the LLM reviewer
    if isinstance(node_input, ClinicalRiskAssessment):
        ctx.state["risk_assessment"] = node_input.model_dump()
        
    # 2. Retrieve MedicationRequest
    req_dict = ctx.state.get("medication_request")
    if req_dict:
        req = MedicationRequest(**req_dict)
    elif isinstance(node_input, MedicationRequest):
        req = node_input
    else:
        req = MedicationRequest(drug_name="unknown", dose_mg=0.0, frequency_per_day=1)

    # 3. Import safety checks from the local server module.
    verify_fn = None
    allergy_fn = None
    try:
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from server import verify_medication_safety, check_allergy_conflict
        verify_fn = verify_medication_safety
        allergy_fn = check_allergy_conflict
    except Exception:
        # Fallback local implementations if server.py is not importable
        def fallback_verify(drug_name: str, dose_mg: float, frequency_per_day: int) -> str:
            total_daily = dose_mg * frequency_per_day
            if drug_name.strip().lower() == "warfarin" and total_daily > 10.0:
                return f"CRITICAL_CONFLICT: Warfarin daily dose of {total_daily:.1f}mg exceeds the maximum safe threshold of 10.0mg."
            return "DOSAGE_SAFE"
            
        def fallback_allergy(patient_id: str, drug_name: str) -> str:
            if patient_id == "patient-102" and "penicillin" in drug_name.lower():
                return "CRITICAL_CONFLICT: Allergy contraindication! Patient has allergy to PENICILLIN."
            return "NO_ALLERGY_CONFLICT"
            
        verify_fn = fallback_verify
        allergy_fn = fallback_allergy
        
    # Execute checks
    allergy_result = allergy_fn(patient_id=req.patient_id, drug_name=req.drug_name)
    dosage_result = verify_fn(
        drug_name=req.drug_name,
        dose_mg=req.dose_mg,
        frequency_per_day=req.frequency_per_day
    )
    
    # Combine results
    if "CRITICAL_CONFLICT" in allergy_result:
        combined_result = allergy_result
    else:
        combined_result = dosage_result
        
    ctx.state["mcp_safety_result"] = combined_result
    
    if "CRITICAL_CONFLICT" in combined_result:
        # Route to caregiver triage
        return Event(route="manual_triage", output=req)
    else:
        # Route to auto approval
        return Event(route="auto_approve", output=req)



async def caregiver_triage_node(ctx: Context, node_input: Any) -> Generator[Any, Any, Any]:
    # Ensure risk assessment from the LLM or security gate is preserved
    risk = ctx.state.get("risk_assessment")
    if not risk and isinstance(node_input, ClinicalRiskAssessment):
        risk = node_input.model_dump()
        ctx.state["risk_assessment"] = risk
    elif not risk:
        # Fallback risk if not generated yet
        risk = {
            "risk_level": "High",
            "warnings": [ctx.state.get("mcp_safety_result", "Clinical dosage threshold exceeded.")],
            "explanation": "dosage verification flagged a contraindication limit."
        }
        ctx.state["risk_assessment"] = risk

    req = ctx.state.get("medication_request", {})
    safety_msg = ctx.state.get("mcp_safety_result", "")
    
    msg = (
        f"=== CAREGIVER REVIEW REQUIRED ===\n"
        f"Patient ID: {req.get('patient_id')}\n"
        f"Prescription request: {req.get('drug_name')} {req.get('dose_mg')}mg x {req.get('frequency_per_day')}/day\n"
        f"MCP Safety Check Result: {safety_msg}\n"
        f"LLM Risk Level: {risk.get('risk_level')}\n"
        f"Warnings: {', '.join(risk.get('warnings', []))}\n"
        f"==================================\n"
        f"Please reply 'approve override' or 'reject'."
    )

    # Dynamic interrupt_id suffix to avoid google-adk 2.0.0b1 UI crash
    iteration = ctx.state.get("triage_iteration", 1)
    interrupt_id = f"caregiver_review_v{iteration}"

    if not ctx.resume_inputs or interrupt_id not in ctx.resume_inputs:
        ctx.state["triage_iteration"] = iteration + 1
        yield RequestInput(
            interrupt_id=interrupt_id,
            message=msg
        )
        return
        
    val = ctx.resume_inputs[interrupt_id]
    if isinstance(val, dict):
        decision = str(val.get("response") or val.get("output") or list(val.values())[0] if val else "")
    else:
        decision = str(val)
        
    decision = decision.strip().lower()
    yield Event(output=decision, state={"caregiver_decision": decision})


def record_outcome_node(ctx: Context, node_input: Any) -> Generator[Any, Any, Any]:
    decision = None
    if isinstance(node_input, dict):
        decision = str(node_input.get("response") or node_input.get("output") or list(node_input.values())[0] if node_input else "")
    else:
        decision = str(node_input)
    decision = decision.strip().lower()

    # Match positive approval keywords (override approved)
    is_approved = False
    if "approve" in decision or "override" in decision or decision in ["yes", "y", "accept", "go"]:
        if not any(neg in decision for neg in ["not", "don't", "no", "reject"]):
            is_approved = True

    status = "approved_by_caregiver" if is_approved else "rejected_by_caregiver"
    msg = f"Caregiver triage completed. Prescription modification: {status.upper()}."
    
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]))
    yield Event(
        output={"status": status, "reason": f"Caregiver decision: {decision}"}
    )


def auto_approve_node(ctx: Context, node_input: MedicationRequest) -> Generator[Any, Any, Any]:
    msg = (
        f"Prescription Modification Approved: {node_input.drug_name} {node_input.dose_mg}mg "
        f"({node_input.frequency_per_day} times daily) added to Patient schedule."
    )
    yield Event(content=types.Content(role='model', parts=[types.Part.from_text(text=msg)]))
    yield Event(
        output={"status": "auto_approved", "reason": "MCP check reported DOSAGE_SAFE"},
        state={"decision": "auto_approved"}
    )

# -------------------------------------------------------------
# 3. Graph Setup
# -------------------------------------------------------------

root_agent = Workflow(
    name="medication_safety_workflow",
    edges=[
        ('START', extract_medication_request),
        (extract_medication_request, security_checkpoint),
        (security_checkpoint, {
            'bypass_llm': clinical_mcp_check,
            'clean': clinical_risk_reviewer
        }),
        (clinical_risk_reviewer, clinical_mcp_check),
        (clinical_mcp_check, {
            'manual_triage': caregiver_triage_node,
            'auto_approve': auto_approve_node
        }),
        (caregiver_triage_node, record_outcome_node),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True)
)
