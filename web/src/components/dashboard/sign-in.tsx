"use client";

import { useId, useState } from "react";
import { Loader2Icon, LogInIcon, ShieldCheckIcon } from "lucide-react";

import { PanelError } from "@/components/dashboard/panel-states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";

/** The access-code screen shown before the dashboard when the server asks for sign-in. */
export function SignIn({
  configured,
  onSignIn,
}: {
  configured: boolean;
  onSignIn: (code: string) => Promise<void>;
}) {
  const inputId = useId();
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!code.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await onSignIn(code);
    } catch (failure) {
      setError(errorMessage(failure));
      setCode("");
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <section
        aria-labelledby="signin-heading"
        className="w-full max-w-md rounded-3xl bg-card p-6 shadow-card sm:p-8"
      >
        <div className="flex items-center gap-3">
          <span aria-hidden className="flex size-12 shrink-0 items-center justify-center rounded-full bg-muted">
            <ShieldCheckIcon className="size-6" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <h1 id="signin-heading" className="font-heading text-3xl leading-tight font-medium tracking-tight">
              AegisMed
            </h1>
            <p className="text-sm text-muted-foreground">Personal Prescription Safety Concierge</p>
          </div>
        </div>

        {configured ? (
          <form onSubmit={handleSubmit} noValidate className="mt-6 grid gap-4">
            <p className="text-base text-pretty">Enter the access code to open the caregiver dashboard.</p>
            <div className="grid gap-1.5">
              <Label htmlFor={inputId}>Access code</Label>
              <Input
                id={inputId}
                type="password"
                value={code}
                onChange={(event) => setCode(event.target.value)}
                autoComplete="off"
                autoFocus
                aria-invalid={error ? true : undefined}
                aria-describedby={error ? `${inputId}-error` : undefined}
                className="h-11 rounded-full px-4"
              />
              {error && (
                <p id={`${inputId}-error`} role="alert" className="text-sm font-medium text-destructive">
                  {error}
                </p>
              )}
            </div>
            <Button type="submit" size="touch" disabled={busy || !code.trim()}>
              {busy ? (
                <Loader2Icon aria-hidden data-icon="inline-start" className="animate-spin" />
              ) : (
                <LogInIcon aria-hidden data-icon="inline-start" />
              )}
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>
        ) : (
          <PanelError
            className="mt-6"
            title="Sign-in is not set up"
            message="This server has no access code configured yet, so it is not serving any data. Ask the person who runs this deployment to set one."
            onRetry={() => window.location.reload()}
          />
        )}
      </section>
    </main>
  );
}
