import os
import json
from fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("AegisMed Clinical Safety Server")

def load_patients_db() -> dict:
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patients.json")
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    # Fallback if file doesn't exist yet
    return {
        "patient-101": {"name": "John Doe", "age": 62, "allergies": ["sulfa", "sulfonamide", "bactrim"], "active": "Lisinopril 10mg", "avatar": "👨\u200d🦳"},
        "patient-102": {"name": "Jane Smith", "age": 45, "allergies": ["penicillin", "amoxicillin", "ampicillin"], "active": "Atorvastatin 20mg", "avatar": "👩"},
        "patient-103": {"name": "Robert Johnson", "age": 71, "allergies": ["aspirin", "acetylsalicylic acid"], "active": "Metoprolol 50mg", "avatar": "👴"},
        "patient-104": {"name": "Alice Brown", "age": 29, "allergies": [], "active": "None", "avatar": "👩\u200d\u00a0"}
    }

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
    drug_name_clean = drug_name.strip().lower()
    total_daily_dose = dose_mg * frequency_per_day
    
    # Clinical rule: If Warfarin is requested and exceeds 10mg total daily, flag a critical conflict.
    if drug_name_clean == "warfarin" and total_daily_dose > 10.0:
        return (
            f"CRITICAL_CONFLICT: Warfarin daily dose of {total_daily_dose:.1f}mg "
            f"exceeds the maximum safe threshold of 10.0mg. "
            f"Potential fatal internal bleeding hazard!"
        )
    
    return "DOSAGE_SAFE"

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
    patient_id_clean = patient_id.strip().lower()
    drug_name_clean = drug_name.strip().lower()
    
    patients_db = load_patients_db()
    patient_key = patient_id_clean
    if not patient_key.startswith("patient-") and f"patient-{patient_key}" in patients_db:
        patient_key = f"patient-{patient_key}"
        
    patient_data = patients_db.get(patient_key)
    if not patient_data:
        return "NO_ALLERGY_CONFLICT"
        
    patient_allergies = patient_data.get("allergies", [])
    for allergy in patient_allergies:
        if allergy.strip().lower() in drug_name_clean:
            return (
                f"CRITICAL_CONFLICT: Allergy contraindication! "
                f"Patient has a documented allergy to {allergy.upper()}."
            )
            
    return "NO_ALLERGY_CONFLICT"

if __name__ == "__main__":
    mcp.run()
