"""Deterministic clinical safety rules.

One implementation, used by both the workflow graph and the FastMCP server.
The result strings are part of the contract: callers look for
``CRITICAL_CONFLICT`` and show the text to caregivers.
"""
from app.config import WARFARIN_THRESHOLD_MG

DOSAGE_SAFE = "DOSAGE_SAFE"
NO_ALLERGY_CONFLICT = "NO_ALLERGY_CONFLICT"
CRITICAL_CONFLICT = "CRITICAL_CONFLICT"


def canonical_patient_id(patient_id: str) -> str:
    """Normalise an id to the stored form: "104" -> "patient-104". "unknown" is kept."""
    cleaned = (patient_id or "unknown").strip().lower()
    if cleaned == "unknown" or cleaned.startswith("patient-"):
        return cleaned
    return f"patient-{cleaned}"


def verify_medication_safety(drug_name: str, dose_mg: float, frequency_per_day: int) -> str:
    """Check the total daily dose against clinical thresholds."""
    total_daily_dose = dose_mg * frequency_per_day
    if drug_name.strip().lower() == "warfarin" and total_daily_dose > WARFARIN_THRESHOLD_MG:
        return (
            f"{CRITICAL_CONFLICT}: Warfarin daily dose of {total_daily_dose:.1f}mg "
            f"exceeds the maximum safe threshold of {WARFARIN_THRESHOLD_MG:.1f}mg. "
            f"Potential fatal internal bleeding hazard!"
        )
    return DOSAGE_SAFE


def check_allergy_conflict(patient_id: str, drug_name: str, patients: dict) -> str:
    """Check a drug against the patient's documented allergies.

    Matching is by name: a conflict is reported when a documented allergen
    appears in the requested drug name. Brand names and drug classes that are
    not listed for the patient are not recognised.
    """
    patient = patients.get(canonical_patient_id(patient_id))
    if not patient:
        return NO_ALLERGY_CONFLICT
    requested = drug_name.strip().lower()
    for allergy in patient.get("allergies", []):
        if allergy.strip().lower() in requested:
            return (
                f"{CRITICAL_CONFLICT}: Allergy contraindication! "
                f"Patient has a documented allergy to {allergy.upper()}."
            )
    return NO_ALLERGY_CONFLICT
