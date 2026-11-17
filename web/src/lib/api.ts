import type {
  AgentResult,
  CaregiverDecision,
  DashboardState,
  NewPatient,
  PatientFilter,
  SessionInfo,
} from "@/lib/types";

/** An API failure with a message that is safe to show to the user. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "Something went wrong. Please try again.";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...init, cache: "no-store", headers: { Accept: "application/json" } });
  } catch {
    throw new ApiError("Could not reach the AegisMed server. Check your connection and try again.", 0);
  }

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON bodies are handled by the status check below.
  }

  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "message" in body && typeof body.message === "string"
        ? body.message
        : `The server returned an error (${response.status}).`;
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

function formBody(fields: Record<string, string>): FormData {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) data.append(key, value);
  return data;
}

/** True when the server says the browser is not signed in (or the session expired). */
export function isSignedOut(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}

export const api = {
  getSession: () => request<SessionInfo>("/api/session"),

  login: (code: string) => request<{ status: string }>("/api/login", { method: "POST", body: formBody({ code }) }),

  logout: () => request<{ status: string }>("/api/logout", { method: "POST" }),

  getState: () => request<DashboardState>("/api/state"),

  sendChat: (message: string, sessionId: string, patient: PatientFilter) =>
    request<AgentResult>("/api/chat", {
      method: "POST",
      body: formBody({ message, session_id: sessionId, user_id: "user-default", patient_id: patient }),
    }),

  resolveAlert: (sessionId: string, decision: CaregiverDecision) =>
    request<AgentResult>("/api/resolve", {
      method: "POST",
      body: formBody({ session_id: sessionId, decision }),
    }),

  addPatient: (patient: NewPatient) =>
    request<{ status: string; patient_id: string }>("/api/patients/add", {
      method: "POST",
      body: formBody(patient),
    }),

  resetDemo: () => request<{ message: string }>("/api/reset", { method: "POST" }),
};
