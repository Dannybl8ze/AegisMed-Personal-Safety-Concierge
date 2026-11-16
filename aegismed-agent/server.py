"""AegisMed Clinical Safety MCP server (FastMCP).

Exposes the shared rule functions from ``app.safety_rules`` as MCP tools.
Run from this directory: ``python server.py`` (needs the ``mcp`` extra).
"""
from fastmcp import FastMCP

from app import safety_rules
from app.storage import get_storage

mcp = FastMCP("AegisMed Clinical Safety Server")


@mcp.tool()
def verify_medication_safety(drug_name: str, dose_mg: float, frequency_per_day: int) -> str:
    """
    Checks if a newly requested medication is safe for the patient's profile.

    Args:
        drug_name: The name of the medication being added (e.g., Warfarin, Aspirin).
        dose_mg: Milligrams per single dose.
        frequency_per_day: Number of doses taken per day.

    Returns:
        A status string indicating whether the dosage is safe or presents a conflict.
    """
    return safety_rules.verify_medication_safety(drug_name, dose_mg, frequency_per_day)


@mcp.tool()
def check_allergy_conflict(patient_id: str, drug_name: str) -> str:
    """
    Checks if a medication conflicts with a patient's documented allergies.

    Args:
        patient_id: The ID of the patient (e.g., patient-101, patient-102).
        drug_name: The name of the medication being requested.

    Returns:
        A status string indicating whether there is an allergy conflict.
    """
    return safety_rules.check_allergy_conflict(patient_id, drug_name, get_storage().get_patients())


if __name__ == "__main__":
    mcp.run()
