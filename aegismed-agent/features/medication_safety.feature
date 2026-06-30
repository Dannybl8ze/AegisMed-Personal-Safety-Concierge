Feature: Medication Safety Checks
  As a patient concierge
  I want to verify medication safety and flag contraindications
  So that patients are protected from drug-to-drug interactions and dangerous dosages.

  Background:
    Given the patient is logged into AegisMed concierge
    And their medication safety profile is loaded

  Scenario: Adding a standard safe medication
    Given the patient's active medication is Aspirin
    When they request to add "Lisinopril 10mg once daily"
    Then the system checks Lisinopril for safety conflicts via MCP
    And the medication Lisinopril is auto-approved and added to the patient schedule

  Scenario: Flagging dangerous drug interaction (High dose Warfarin)
    Given the patient is currently taking medication
    When they attempt to add "Warfarin 6mg twice daily" to their profile
    Then the MCP server calculates the total daily dose is 12.0mg
    And the system flags a CRITICAL_CONFLICT warning
    And the safety workflow pauses for caregiver override using caregiver_review_v1
    And a pending alert is published to the caregiver dashboard
