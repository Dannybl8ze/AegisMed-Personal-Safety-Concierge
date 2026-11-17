"use client";

import { useId } from "react";
import {
  BanIcon,
  CircleHelpIcon,
  Loader2Icon,
  LocateFixedIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  TriangleAlertIcon,
} from "lucide-react";

import { RiskMeter } from "@/components/dashboard/status-badges";
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { alertKind, findPatient, medicationLabel, safetyText } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { CaregiverDecision, Patients, SafetyAlert } from "@/lib/types";

/** How each kind of hold looks: wording, icon and colours. Colour is never the only signal. */
const KIND_LOOK = {
  security: {
    Icon: ShieldAlertIcon,
    kicker: "Security hold",
    heading: "Security hold:",
    badge: "bg-surface-danger text-destructive",
    box: "bg-surface-danger text-on-surface-danger",
  },
  review: {
    Icon: CircleHelpIcon,
    kicker: "Needs review",
    heading: "Needs review:",
    badge: "bg-surface-info text-info",
    box: "bg-surface-info text-on-surface-info",
  },
  contraindication: {
    Icon: TriangleAlertIcon,
    kicker: "Contraindication",
    heading: "Contraindication flagged:",
    badge: "bg-surface-warning text-warning",
    box: "bg-surface-warning text-on-surface-warning",
  },
} as const;

/*
 * Adapted from "Alert with Icon and Actions" by @cnippet-dev on 21st.dev
 * (component 23620): a leading icon, a title, a description and an action row
 * of confirm/dismiss buttons. The description was extended to carry the safety
 * result, warnings and assessment, and the actions became 44px pill buttons.
 */
export function AlertCard({
  alert,
  patients,
  resolving,
  onResolve,
  onLocate,
}: {
  alert: SafetyAlert;
  patients: Patients;
  resolving?: CaregiverDecision;
  onResolve: (sessionId: string, decision: CaregiverDecision) => void;
  onLocate: (sessionId: string) => void;
}) {
  const titleId = useId();
  const kind = alertKind(alert);
  const look = KIND_LOOK[kind];
  const Icon = look.Icon;
  const patient = findPatient(patients, alert.patient_id);
  const shownResult = safetyText(alert);
  // Reasons already quoted in the result box are not listed again below it.
  const extraWarnings = alert.warnings.filter(
    (warning) => warning !== alert.safety_result && !shownResult.includes(warning),
  );
  const busy = resolving !== undefined;

  return (
    <Alert
      role="article"
      aria-labelledby={titleId}
      aria-busy={busy}
      className="flex flex-col gap-4 rounded-3xl border-0 bg-card p-5 shadow-card has-data-[slot=alert-action]:pr-5"
    >
      {/* On narrow screens the title drops below the icon and meter so it is not squeezed. */}
      <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
        <span
          aria-hidden
          className={cn("flex size-11 shrink-0 items-center justify-center rounded-full", look.badge)}
        >
          <Icon className="size-5" />
        </span>
        <div className="order-last min-w-0 basis-full sm:order-none sm:flex-1 sm:basis-0">
          <p className="text-sm text-muted-foreground">
            {look.kicker} <span aria-hidden>·</span> Patient ID:{" "}
            {alert.patient_id}
            {patient ? ` · ${patient.name}` : ""}
          </p>
          <AlertTitle id={titleId} className="font-heading text-2xl leading-tight font-medium tracking-tight break-words">
            {medicationLabel(alert)}
          </AlertTitle>
        </div>
        <RiskMeter level={alert.risk_level} className="ml-auto" />
      </div>

      <AlertDescription className="grid gap-3 text-base text-card-foreground md:text-pretty">
        <div className={cn("rounded-2xl px-4 py-3", look.box)}>
          <p className="font-semibold">{look.heading}</p>
          <p className="break-words">{shownResult}</p>
        </div>

        {extraWarnings.length > 0 && (
          <div>
            <p className="font-semibold">Warnings</p>
            <ul className="mt-1 grid gap-1">
              {extraWarnings.map((warning) => (
                <li key={warning} className="flex gap-2 text-muted-foreground">
                  <TriangleAlertIcon aria-hidden className="mt-1 size-4 shrink-0 text-warning" />
                  <span className="break-words">{warning}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {alert.explanation && (
          <p className="break-words text-muted-foreground">
            <span className="font-semibold text-card-foreground">AI Assessment:</span> {alert.explanation}
          </p>
        )}
      </AlertDescription>

      <AlertAction className="static flex flex-wrap gap-2">
        <Button
          size="touch"
          disabled={busy}
          onClick={() => onResolve(alert.session_id, "approve override")}
          className="flex-1 bg-caution text-caution-foreground hover:bg-caution/85"
        >
          {resolving === "approve override" ? (
            <Loader2Icon aria-hidden data-icon="inline-start" className="animate-spin" />
          ) : (
            <ShieldCheckIcon aria-hidden data-icon="inline-start" />
          )}
          {resolving === "approve override" ? "Approving…" : "Approve Override"}
        </Button>
        <Button
          variant="outline"
          size="touch"
          disabled={busy}
          onClick={() => onResolve(alert.session_id, "reject")}
          className="flex-1"
        >
          {resolving === "reject" ? (
            <Loader2Icon aria-hidden data-icon="inline-start" className="animate-spin" />
          ) : (
            <BanIcon aria-hidden data-icon="inline-start" />
          )}
          {resolving === "reject" ? "Rejecting…" : "Reject Request"}
        </Button>
        <Button variant="ghost" size="touch" onClick={() => onLocate(alert.session_id)} className="w-full sm:w-auto">
          <LocateFixedIcon aria-hidden data-icon="inline-start" />
          Locate in Sandbox
        </Button>
      </AlertAction>
    </Alert>
  );
}
