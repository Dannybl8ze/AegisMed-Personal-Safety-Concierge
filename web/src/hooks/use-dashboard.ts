"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { toast } from "sonner";

import { ApiError, api, errorMessage, isSignedOut } from "@/lib/api";
import { ALL_PATIENTS, newSessionId } from "@/lib/format";
import type { CaregiverDecision, DashboardState, NewPatient, PatientFilter } from "@/lib/types";

/** A message that has been sent but not yet answered. */
export type PendingChat = { text: string; sessionId: string; patientId: string };

/** A message the server could not process; shown until the next attempt. */
export type ChatFailure = PendingChat & { reason: string };

const subscribeNoop = () => () => {};

/** False on the server and during hydration, true afterwards. */
export function useHydrated(): boolean {
  return useSyncExternalStore(subscribeNoop, () => true, () => false);
}

/**
 * All dashboard data and actions. `onSignedOut` is called when the server answers
 * 401, which means the session ended while the page was open.
 */
export function useDashboard(onSignedOut?: () => void) {
  const [data, setData] = useState<DashboardState | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [pendingChat, setPendingChat] = useState<PendingChat | null>(null);
  const [chatFailure, setChatFailure] = useState<ChatFailure | null>(null);
  const [resolving, setResolving] = useState<Record<string, CaregiverDecision>>({});
  const [sessionId, setSessionId] = useState(newSessionId);

  const signedOutRef = useRef(onSignedOut);
  useEffect(() => {
    signedOutRef.current = onSignedOut;
  });
  /** Returns true when the error was a lost session (and the sign-in screen is taking over). */
  const lostSession = useCallback((error: unknown): boolean => {
    if (!isSignedOut(error)) return false;
    signedOutRef.current?.();
    return true;
  }, []);

  const refresh = useCallback(async (): Promise<boolean> => {
    try {
      const fresh = await api.getState();
      setData(fresh);
      setLoadError(null);
      return true;
    } catch (error) {
      if (!lostSession(error)) setLoadError(errorMessage(error));
      return false;
    }
  }, [lostSession]);

  // Initial load.
  useEffect(() => {
    let cancelled = false;
    api.getState().then(
      (fresh) => {
        if (cancelled) return;
        setData(fresh);
        setLoadError(null);
      },
      (error) => {
        if (!cancelled && !lostSession(error)) setLoadError(errorMessage(error));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [lostSession]);

  const sendMessage = useCallback(
    async (rawText: string, selected: PatientFilter): Promise<boolean> => {
      let text = rawText.trim();
      if (!text || pendingChat) return false;
      // A request typed while one patient is selected is about that patient.
      if (selected !== ALL_PATIENTS && !text.toLowerCase().includes("patient")) {
        text += ` for ${selected}`;
      }

      const pending: PendingChat = {
        text,
        sessionId,
        patientId: selected === ALL_PATIENTS ? "unknown" : selected,
      };
      setChatFailure(null);
      setPendingChat(pending);

      try {
        await api.sendChat(text, sessionId, selected);
      } catch (error) {
        setPendingChat(null);
        if (lostSession(error)) return false;
        const reason = errorMessage(error);
        setChatFailure({ ...pending, reason });
        setSessionId(newSessionId());
        toast.error("The safety check could not be completed", { description: reason });
        return false;
      }

      // Swap the optimistic bubble for the stored conversation in one render.
      try {
        const fresh = await api.getState();
        setData(fresh);
        setLoadError(null);
      } catch (error) {
        if (!lostSession(error)) setLoadError(errorMessage(error));
      }
      setPendingChat(null);
      setSessionId(newSessionId());
      return true;
    },
    [lostSession, pendingChat, sessionId],
  );

  const resolveAlert = useCallback(
    async (alertSessionId: string, decision: CaregiverDecision): Promise<void> => {
      setResolving((current) => ({ ...current, [alertSessionId]: decision }));
      try {
        const result = await api.resolveAlert(alertSessionId, decision);
        await refresh();
        toast.success(decision === "approve override" ? "Override approved" : "Request rejected", {
          description: result.response,
        });
      } catch (error) {
        if (!lostSession(error)) {
          toast.error("The decision was not recorded", { description: errorMessage(error) });
          // 404/409 mean the alert changed elsewhere, so show the current state.
          if (error instanceof ApiError && (error.status === 404 || error.status === 409)) {
            await refresh();
          }
        }
      } finally {
        setResolving((current) => {
          const next = { ...current };
          delete next[alertSessionId];
          return next;
        });
      }
    },
    [lostSession, refresh],
  );

  const addPatient = useCallback(
    async (patient: NewPatient): Promise<boolean> => {
      try {
        const saved = await api.addPatient(patient);
        await refresh();
        toast.success("Patient registered", { description: `${patient.name.trim()} (${saved.patient_id})` });
        return true;
      } catch (error) {
        if (!lostSession(error)) toast.error("The patient was not saved", { description: errorMessage(error) });
        return false;
      }
    },
    [lostSession, refresh],
  );

  const resetDemo = useCallback(async (): Promise<boolean> => {
    try {
      await api.resetDemo();
      setChatFailure(null);
      await refresh();
      toast.success("Demo state reset", { description: "Chat history and alerts were cleared. Patients were kept." });
      return true;
    } catch (error) {
      if (!lostSession(error)) toast.error("The demo state was not reset", { description: errorMessage(error) });
      return false;
    }
  }, [lostSession, refresh]);

  return {
    data,
    loadError,
    isLoading: data === null && loadError === null,
    pendingChat,
    chatFailure,
    resolving,
    sessionId,
    refresh,
    sendMessage,
    resolveAlert,
    addPatient,
    resetDemo,
  };
}

export type Dashboard = ReturnType<typeof useDashboard>;
