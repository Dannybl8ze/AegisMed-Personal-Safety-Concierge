/** Shapes returned by the AegisMed API (see aegismed-agent/dashboard_api/main.py). */

export type Patient = {
  name: string;
  age: number;
  allergies: string[];
  active: string;
  avatar?: string;
};

export type Patients = Record<string, Patient>;

export type ChatSender = "user" | "agent" | "caregiver";

export type ChatMessage = {
  sender: ChatSender;
  text: string;
  status?: string | null;
  session_id?: string;
  patient_id?: string;
  /** Server-local "HH:MM" (legacy field). */
  timestamp?: string;
  /** UTC ISO timestamp. */
  ts?: string;
};

export type AlertStatus = "pending" | "approved" | "rejected";

export type SafetyAlert = {
  session_id: string;
  user_id: string;
  patient_id: string;
  drug_name: string;
  dose_mg: number;
  frequency_per_day: number;
  safety_result: string;
  risk_level: string;
  warnings: string[];
  explanation: string;
  interrupt_id: string;
  status: AlertStatus;
};

export type SessionInfo = {
  /** Whether this deployment asks people to sign in. */
  required: boolean;
  authenticated: boolean;
  /** False when sign-in is required but the server has no access code set. */
  configured: boolean;
};

export type DashboardState = {
  patients: Patients;
  history: ChatMessage[];
  pending: SafetyAlert[];
  resolved: SafetyAlert[];
};

export type AgentResult = {
  status: "completed" | "paused";
  session_id: string;
  response: string;
  patient_id?: string;
};

export type CaregiverDecision = "approve override" | "reject";

export type NewPatient = {
  patient_id: string;
  name: string;
  age: string;
  allergies: string;
  active: string;
};

/** "all" or a patient id such as "patient-101". */
export type PatientFilter = string;
