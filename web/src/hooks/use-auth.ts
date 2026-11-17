"use client";

import { useCallback, useEffect, useState } from "react";

import { api, errorMessage } from "@/lib/api";
import type { SessionInfo } from "@/lib/types";

export type AuthState =
  | { phase: "checking" }
  | { phase: "unreachable"; message: string }
  | { phase: "signed-out"; configured: boolean }
  | { phase: "ready"; required: boolean };

function fromSession(session: SessionInfo): AuthState {
  if (!session.required || session.authenticated) return { phase: "ready", required: session.required };
  return { phase: "signed-out", configured: session.configured };
}

/** Whether this browser may use the dashboard, and how to sign in and out. */
export function useAuth() {
  const [state, setState] = useState<AuthState>({ phase: "checking" });

  // Initial check.
  useEffect(() => {
    let cancelled = false;
    api.getSession().then(
      (session) => {
        if (!cancelled) setState(fromSession(session));
      },
      (error) => {
        if (!cancelled) setState({ phase: "unreachable", message: errorMessage(error) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const retry = useCallback(() => {
    setState({ phase: "checking" });
    api.getSession().then(
      (session) => setState(fromSession(session)),
      (error) => setState({ phase: "unreachable", message: errorMessage(error) }),
    );
  }, []);

  /** Rejects with an ApiError whose message is safe to show (wrong code, locked out). */
  const signIn = useCallback(async (code: string) => {
    await api.login(code);
    setState(fromSession(await api.getSession()));
  }, []);

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setState({ phase: "signed-out", configured: true });
    }
  }, []);

  /** The server answered 401: the session ended while the dashboard was open. */
  const expire = useCallback(() => {
    setState((current) => (current.phase === "ready" ? { phase: "signed-out", configured: true } : current));
  }, []);

  return { state, signIn, signOut, expire, retry };
}
