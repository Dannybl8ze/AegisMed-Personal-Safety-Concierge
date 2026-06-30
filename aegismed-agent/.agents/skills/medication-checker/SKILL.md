---
name: medication-checker
description: Analyzes active prescriptions and schedules for clinical safety. Use this skill when adding or modifying medications.
---

# Medication Checker Skill

This skill governs the verification of newly added or modified medications for patient safety. It acts as the L2/L3 execution instruction guide when medication requests are made.

## Context and Instructions
When this skill is invoked, you must parse the active drug profile from the system assets or user's message.

## Execution Rules
1. Extract the name, single-dose milligrams, and daily intake frequency of the drug from the user's input message.
2. Call the `verify_medication_safety` tool from the FastMCP server, passing:
   - `drug_name`: Cleaned name of the drug.
   - `dose_mg`: Extracted single dose in milligrams.
   - `frequency_per_day`: Number of intakes per day.
3. Check the output of the tool:
   - If the output contains `CRITICAL_CONFLICT`, stop immediately, set the workflow status to `BLOCKED`, flag the conflict in the session logs, and alert the primary caregiver for manual approval.
   - If the output is `DOSAGE_SAFE`, set status to `APPROVED` and update the patient's schedule.
