import type { ChatMessage, Patient, PatientFilter, Patients, SafetyAlert } from "@/lib/types";

export const ALL_PATIENTS: PatientFilter = "all";

/** "patient-101" and "101" both become "101"; missing ids become "unknown". */
export function normalizePatientId(patientId: string | null | undefined): string {
  if (!patientId) return "unknown";
  return patientId.trim().toLowerCase().replace("patient-", "");
}

export function findPatient(patients: Patients, patientId: string | null | undefined): Patient | undefined {
  const wanted = normalizePatientId(patientId);
  const key = Object.keys(patients).find((id) => normalizePatientId(id) === wanted);
  return key ? patients[key] : undefined;
}

/** "John Doe (ID: 101)" */
export function patientLabel(patientId: string, patient: Patient): string {
  return `${patient.name} (ID: ${normalizePatientId(patientId)})`;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase() || "?";
}

export function allergySummary(patient: Patient): string {
  if (!patient.allergies?.length) return "None";
  return patient.allergies.map((a) => a.charAt(0).toUpperCase() + a.slice(1)).join(", ");
}

/** Does an item belong in the current patient view? */
export function matchesPatient(
  selected: PatientFilter,
  patientId: string | null | undefined,
  options: { includeUnknown?: boolean } = {},
): boolean {
  if (selected === ALL_PATIENTS) return true;
  const id = normalizePatientId(patientId);
  if (id === "unknown") return Boolean(options.includeUnknown);
  return id === normalizePatientId(selected);
}

/** Doses print like the API's numbers do: 6 -> "6.0", 2.5 -> "2.5". */
export function formatDose(dose: number): string {
  return Number.isInteger(dose) ? dose.toFixed(1) : String(dose);
}

/** "Warfarin 6.0mg x 2/day"; requests the parser could not read say so instead of "unknown 0.0mg". */
export function medicationLabel(alert: SafetyAlert): string {
  const drug = alert.drug_name.trim().toLowerCase() === "unknown" ? "Unrecognised medication" : alert.drug_name;
  const dose = alert.dose_mg > 0 ? `${formatDose(alert.dose_mg)}mg` : "dose not read";
  return `${drug} ${dose} x ${alert.frequency_per_day}/day`;
}

/** Why the request is waiting for a caregiver. */
export type AlertKind = "security" | "review" | "contraindication";

const REVIEW_PREFIX = "REVIEW_REQUIRED:";

export function alertKind(alert: SafetyAlert): AlertKind {
  if (alert.safety_result.startsWith("SECURITY_HOLD") || alert.warnings.some((w) => w.startsWith("SECURITY EVENT"))) {
    return "security";
  }
  return alert.safety_result.startsWith(REVIEW_PREFIX) ? "review" : "contraindication";
}

/** The safety result as shown to people: review reasons without their machine prefix. */
export function safetyText(alert: SafetyAlert): string {
  return alert.safety_result.startsWith(REVIEW_PREFIX)
    ? alert.safety_result.slice(REVIEW_PREFIX.length).trim()
    : alert.safety_result;
}

/** Local "HH:MM" for a chat message, falling back to the server's own clock string. */
export function messageTime(message: ChatMessage): string {
  if (message.ts) {
    const date = new Date(message.ts);
    if (!Number.isNaN(date.getTime())) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    }
  }
  return message.timestamp ?? "";
}

/** The API prefixes held requests with an emoji; the UI shows an icon instead. */
export function stripLeadingEmoji(text: string): string {
  return text.replace(/^[^\p{L}\p{N}]+/u, "");
}

export function newSessionId(): string {
  return `session-${Math.random().toString(36).slice(2, 11)}`;
}

function csvField(value: string): string {
  return `"${value.replace(/,/g, " ").replace(/"/g, '""')}"`;
}

/** Audit export: one row per resolved alert, with the columns the portal has always used. */
export function buildAuditCsv(resolved: SafetyAlert[]): string {
  const rows = resolved.map((alert) =>
    [alert.patient_id, medicationLabel(alert), alert.status.toUpperCase()].map(csvField).join(","),
  );
  return ["Patient ID,Prescribed Medication,Caregiver Action", ...rows].join("\n") + "\n";
}

export function auditFileName(date: Date = new Date()): string {
  return `AegisMed_Override_Audit_Log_${date.toISOString().slice(0, 10)}.csv`;
}
