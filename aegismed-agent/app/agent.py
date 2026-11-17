"""AegisMed medication-safety workflow (Google ADK graph).

START -> extract -> security gate -> [LLM reviewer] -> rule checks
      -> auto-approve | caregiver review (pause/resume) -> record outcome
"""
import asyncio
import base64
import json
import logging
from typing import Any, AsyncGenerator, Generator, List, Optional

from google.adk.agents import LlmAgent
from google.adk.agents.context import Context
from google.adk.apps import App, ResumabilityConfig
from google.adk.events.event import Event
from google.adk.events.request_input import RequestInput
from google.adk.models import Gemini
from google.adk.workflow import Workflow
from google.genai import types
from pydantic import BaseModel, Field

from app.config import (
    GEMINI_CALL_TIMEOUT_SECONDS,
    GEMINI_PRIMARY_TIMEOUT_SECONDS,
    MODEL_NAME,
    fallback_model,
    thinking_level,
)
from app.extraction import parse_medication_text
from app.safety_rules import (
    CRITICAL_CONFLICT,
    REVIEW_REQUIRED,
    check_allergy_conflict,
    review_reasons,
    verify_medication_safety,
)
from app.security import is_prompt_injection, redact_pii
from app.storage import get_storage

LLM_REVIEWER_NAME = "clinical_risk_reviewer"

logger = logging.getLogger(__name__)


def is_temporary_gemini_error(error: BaseException) -> bool:
    """Timeouts, rate limits and server-side failures: worth trying another model for."""
    return isinstance(error, TimeoutError) or getattr(error, "code", None) in (429, 500, 502, 503, 504)


class LoopSafeGemini(Gemini):
    """Gemini model that rebuilds its API client when the running event loop changes.

    The client holds loop-bound network resources, so one built on an earlier
    loop cannot be reused. Authentication comes from the environment (see
    ``app.config``); nothing is hard-coded here.
    """

    @property
    def api_client(self):
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self.__dict__.get("_cached_loop") is not current_loop:
            self.__dict__.pop("api_client", None)
            self.__dict__["_cached_loop"] = current_loop

        if "api_client" not in self.__dict__:
            self.__dict__["api_client"] = Gemini.api_client.func(self)
        return self.__dict__["api_client"]

    async def generate_content_async(self, llm_request, stream=False):
        fallback = fallback_model(self.model)
        if fallback is None:
            async with asyncio.timeout(GEMINI_CALL_TIMEOUT_SECONDS):
                async for response in super().generate_content_async(llm_request, stream=stream):
                    yield response
            return

        # The primary model gets a shorter time limit; if it is slow, busy or down,
        # the same request is tried once more on the fallback model.
        answered = False
        try:
            async with asyncio.timeout(GEMINI_PRIMARY_TIMEOUT_SECONDS):
                async for response in super().generate_content_async(llm_request, stream=stream):
                    answered = True
                    yield response
            return
        except Exception as error:
            if answered or not is_temporary_gemini_error(error):
                raise
            logger.warning(
                "Gemini model %s failed (%s); retrying with %s", self.model, type(error).__name__, fallback
            )

        retry_request = llm_request.model_copy(deep=True)
        retry_request.model = fallback
        if retry_request.config is not None:
            level = thinking_level(fallback)
            retry_request.config.thinking_config = (
                types.ThinkingConfig(thinking_level=types.ThinkingLevel[level]) if level else None
            )
        async with asyncio.timeout(GEMINI_CALL_TIMEOUT_SECONDS):
            async for response in super().generate_content_async(retry_request, stream=stream):
                yield response


# Temporary Gemini errors (overload, rate limits) are retried a few times with backoff.
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=3,
    initial_delay=1.0,
    max_delay=10.0,
    exp_base=2.0,
    jitter=0.5,
    http_status_codes=[429, 500, 502, 503, 504],
)


def reviewer_generation_config(model_name: str) -> "types.GenerateContentConfig | None":
    """Generation settings for the reviewer: a low thinking level on Gemini 3 models."""
    level = thinking_level(model_name)
    if level is None:
        return None
    return types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel[level]))


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

    # 1. types.Content (from UI/API), 2. plain string, 3. dictionary
    if hasattr(node_input, "parts") and node_input.parts:
        raw_str = "".join(part.text for part in node_input.parts if part.text)
    elif isinstance(node_input, str):
        raw_str = node_input
    elif isinstance(node_input, dict):
        parsed = node_input

    if raw_str:
        try:
            parsed = json.loads(raw_str)
        except Exception:
            parsed = None
        if not isinstance(parsed, dict):
            parsed = parse_medication_text(raw_str)

    if not parsed:
        raise ValueError(f"Unable to parse input: {node_input}")

    # Payloads may arrive wrapped as {"data": <dict | JSON string | base64 JSON>}
    if "data" in parsed:
        data_val = parsed["data"]
        if isinstance(data_val, str):
            try:
                parsed = json.loads(base64.b64decode(data_val).decode("utf-8"))
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
        notes=str(parsed.get("notes", "")),
    )

    return Event(output=request, state={"medication_request": request.model_dump(), "redacted_categories": []})


def security_checkpoint(ctx: Context, node_input: MedicationRequest) -> Event:
    # 1. Scrub SSNs and phone numbers before anything reaches the LLM
    node_input.notes, redacted_categories = redact_pii(node_input.notes)
    ctx.state["medication_request"] = node_input.model_dump()
    ctx.state["redacted_categories"] = redacted_categories

    # 2. Detect prompt injection: skip the LLM and flag the request
    if is_prompt_injection(node_input.notes):
        ctx.state["security_event"] = True
        ctx.state["risk_assessment"] = {
            "risk_level": "High",
            "warnings": ["SECURITY EVENT: Prompt injection attempt detected in medication request notes!"],
            "explanation": "The request notes triggered security filters due to prompt injection keywords.",
        }
        return Event(route="bypass_llm", output=node_input)

    ctx.state["security_event"] = False
    return Event(route="clean", output=node_input)


# LLM node: assess secondary clinical risk/warnings
clinical_risk_reviewer = LlmAgent(
    name=LLM_REVIEWER_NAME,
    model=LoopSafeGemini(model=MODEL_NAME, retry_options=RETRY_OPTIONS),
    generate_content_config=reviewer_generation_config(MODEL_NAME),
    instruction=(
        "You are a clinical safety reviewer. Review the following medication request "
        "and determine its general risk level (Low, Medium, or High) based on standard safety guidelines. "
        "Highlight any general warnings or guidance for this drug class."
    ),
    output_schema=ClinicalRiskAssessment,
)


def _llm_assessment(node_input: Any) -> Optional[dict]:
    """The reviewer's assessment as a dict, whatever form the node delivered it in."""
    if isinstance(node_input, ClinicalRiskAssessment):
        return node_input.model_dump()
    if isinstance(node_input, str):
        try:
            node_input = json.loads(node_input)
        except Exception:
            return None
    if isinstance(node_input, dict) and "risk_level" in node_input:
        try:
            return ClinicalRiskAssessment(**node_input).model_dump()
        except Exception:
            return None
    return None


def clinical_mcp_check(ctx: Context, node_input: Any) -> Event:
    assessment = _llm_assessment(node_input)

    req_dict = ctx.state.get("medication_request")
    if req_dict:
        req = MedicationRequest(**req_dict)
    elif isinstance(node_input, MedicationRequest):
        req = node_input
    else:
        req = MedicationRequest(drug_name="unknown", dose_mg=0.0, frequency_per_day=1)

    # Deterministic rules: allergy first, then dosage
    patients = get_storage().get_patients()
    allergy_result = check_allergy_conflict(req.patient_id, req.drug_name, patients)
    dosage_result = verify_medication_safety(req.drug_name, req.dose_mg, req.frequency_per_day)
    rule_result = allergy_result if CRITICAL_CONFLICT in allergy_result else dosage_result
    has_conflict = CRITICAL_CONFLICT in rule_result
    security_event = bool(ctx.state.get("security_event"))
    reasons = review_reasons(req.patient_id, req.drug_name, req.dose_mg, patients)

    if security_event:
        # The security gate already recorded a High-risk assessment.
        risk = dict(ctx.state.get("risk_assessment") or {})
        if has_conflict:
            risk["warnings"] = [*risk.get("warnings", []), rule_result]
        risk["warnings"] = [*risk.get("warnings", []), *reasons]
        safety_result = rule_result if has_conflict else (
            "SECURITY_HOLD: Prompt-injection attempt detected; request held for caregiver review. "
            f"Rule checks: {rule_result}."
        )
    elif has_conflict:
        # A rule conflict is always High risk; the reviewer adds context.
        risk = {
            "risk_level": "High",
            "warnings": [rule_result, *reasons, *(assessment["warnings"] if assessment else [])],
            "explanation": assessment["explanation"] if assessment else "Rule-based safety check flagged a contraindication.",
        }
        safety_result = rule_result
    elif reasons:
        # The checks could not run properly, so a caregiver decides instead of the rules.
        risk = {
            "risk_level": "Medium",
            "warnings": [*reasons, *(assessment["warnings"] if assessment else [])],
            "explanation": assessment["explanation"] if assessment else "The request could not be fully checked automatically.",
        }
        safety_result = f"{REVIEW_REQUIRED}: {' '.join(reasons)}"
    else:
        risk = assessment
        safety_result = rule_result

    ctx.state["mcp_safety_result"] = safety_result
    ctx.state["review_reasons"] = reasons
    if risk:
        ctx.state["risk_assessment"] = risk

    if has_conflict or security_event or reasons:
        return Event(route="manual_triage", output=req)
    return Event(route="auto_approve", output=req)


async def caregiver_triage_node(ctx: Context, node_input: Any) -> AsyncGenerator[Any, None]:
    risk = ctx.state.get("risk_assessment") or {}
    req = ctx.state.get("medication_request", {})
    safety_msg = ctx.state.get("mcp_safety_result", "")

    msg = (
        f"=== CAREGIVER REVIEW REQUIRED ===\n"
        f"Patient ID: {req.get('patient_id')}\n"
        f"Prescription request: {req.get('drug_name')} {req.get('dose_mg')}mg x {req.get('frequency_per_day')}/day\n"
        f"MCP Safety Check Result: {safety_msg}\n"
        f"Risk Level: {risk.get('risk_level')}\n"
        f"Warnings: {', '.join(risk.get('warnings', []))}\n"
        f"==================================\n"
        f"Please reply 'approve override' or 'reject'."
    )

    # Dynamic interrupt_id suffix to avoid google-adk 2.0.0b1 UI crash
    iteration = ctx.state.get("triage_iteration", 1)
    interrupt_id = f"caregiver_review_v{iteration}"

    if not ctx.resume_inputs or interrupt_id not in ctx.resume_inputs:
        ctx.state["triage_iteration"] = iteration + 1
        yield RequestInput(interrupt_id=interrupt_id, message=msg)
        return

    val = ctx.resume_inputs[interrupt_id]
    if isinstance(val, dict):
        decision = str(val.get("response") or val.get("output") or list(val.values())[0] if val else "")
    else:
        decision = str(val)

    decision = decision.strip().lower()
    yield Event(output=decision, state={"caregiver_decision": decision})


def record_outcome_node(ctx: Context, node_input: Any) -> Generator[Any, Any, Any]:
    if isinstance(node_input, dict):
        decision = str(node_input.get("response") or node_input.get("output") or list(node_input.values())[0] if node_input else "")
    else:
        decision = str(node_input)
    decision = decision.strip().lower()

    # Positive approval keywords, unless negated
    is_approved = False
    if "approve" in decision or "override" in decision or decision in ["yes", "y", "accept", "go"]:
        if not any(neg in decision for neg in ["not", "don't", "no", "reject"]):
            is_approved = True

    status = "approved_by_caregiver" if is_approved else "rejected_by_caregiver"
    msg = f"Caregiver triage completed. Prescription modification: {status.upper()}."

    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]))
    yield Event(output={"status": status, "reason": f"Caregiver decision: {decision}"})


def auto_approve_node(ctx: Context, node_input: MedicationRequest) -> Generator[Any, Any, Any]:
    msg = (
        f"Prescription Modification Approved: {node_input.drug_name} {node_input.dose_mg}mg "
        f"({node_input.frequency_per_day} times daily) added to Patient schedule."
    )
    yield Event(content=types.Content(role="model", parts=[types.Part.from_text(text=msg)]))
    yield Event(
        output={"status": "auto_approved", "reason": "MCP check reported DOSAGE_SAFE"},
        state={"decision": "auto_approved"},
    )


# -------------------------------------------------------------
# 3. Graph Setup
# -------------------------------------------------------------

root_agent = Workflow(
    name="medication_safety_workflow",
    edges=[
        ("START", extract_medication_request),
        (extract_medication_request, security_checkpoint),
        (security_checkpoint, {
            "bypass_llm": clinical_mcp_check,
            "clean": clinical_risk_reviewer,
        }),
        (clinical_risk_reviewer, clinical_mcp_check),
        (clinical_mcp_check, {
            "manual_triage": caregiver_triage_node,
            "auto_approve": auto_approve_node,
        }),
        (caregiver_triage_node, record_outcome_node),
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
    resumability_config=ResumabilityConfig(is_resumable=True),
)
