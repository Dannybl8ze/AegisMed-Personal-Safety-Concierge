"use client";

import { DownloadIcon, ShieldCheckIcon } from "lucide-react";
import { toast } from "sonner";

import { AlertCard } from "@/components/dashboard/alert-card";
import { DecisionsTable } from "@/components/dashboard/decisions-table";
import { EmptyState, PanelError } from "@/components/dashboard/panel-states";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { Dashboard } from "@/hooks/use-dashboard";
import { ALL_PATIENTS, auditFileName, buildAuditCsv, matchesPatient } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { PatientFilter, SafetyAlert } from "@/lib/types";

function downloadAuditLog(resolved: SafetyAlert[]) {
  if (resolved.length === 0) {
    toast.info("No override decisions log available to export.");
    return;
  }
  const fileName = auditFileName();
  const url = URL.createObjectURL(new Blob([buildAuditCsv(resolved)], { type: "text/csv;charset=utf-8;" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  toast.success("Audit log exported", { description: `${resolved.length} decision(s) saved as ${fileName}` });
}

/** One figure of the summary trio beside the heading. */
function Stat({ value, label }: { value: number | undefined; label: string }) {
  return (
    <div className="flex flex-col-reverse">
      <dt className="text-sm text-muted-foreground">{label}</dt>
      <dd className="font-heading text-4xl leading-none font-light tabular-nums">
        {value === undefined ? <Skeleton className="h-9 w-8 rounded-lg" /> : value}
      </dd>
    </div>
  );
}

const sectionLabel = "px-1 text-sm font-medium text-muted-foreground";

export function ReviewPortal({
  dashboard,
  selected,
  onLocate,
  className,
}: {
  dashboard: Dashboard;
  selected: PatientFilter;
  onLocate: (sessionId: string) => void;
  className?: string;
}) {
  const { data, loadError, isLoading, resolving, resolveAlert, refresh } = dashboard;
  const pending = (data?.pending ?? []).filter((alert) => matchesPatient(selected, alert.patient_id));
  const resolved = (data?.resolved ?? []).filter((alert) => matchesPatient(selected, alert.patient_id));
  const filtered = selected !== ALL_PATIENTS;

  return (
    <section aria-labelledby="portal-heading" className={cn("flex flex-col gap-5", className)}>
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4 px-1 pt-1">
        <h2
          id="portal-heading"
          className="font-heading text-[2.75rem] leading-[0.95] font-light tracking-tight sm:text-6xl"
        >
          Caregiver <br />
          Review Portal
        </h2>
        <dl className="flex gap-7">
          <Stat value={data ? pending.length : undefined} label="Pending" />
          <Stat value={data ? resolved.length : undefined} label="Resolved" />
          <Stat value={data ? Object.keys(data.patients).length : undefined} label="Patients" />
        </dl>
      </div>

      {loadError && !data ? (
        <PanelError title="Alerts could not be loaded" message={loadError} onRetry={() => void refresh()} />
      ) : (
        <>
          <div className="flex flex-col gap-3" aria-busy={isLoading}>
            <h3 id="alerts-heading" tabIndex={-1} className={sectionLabel}>
              Active Security &amp; Contraindication Alerts
            </h3>

            {isLoading && (
              <div role="status" className="flex flex-col gap-3">
                <span className="sr-only">Loading alerts…</span>
                <Skeleton className="h-48 rounded-3xl bg-card" />
                <Skeleton className="h-48 rounded-3xl bg-card" />
              </div>
            )}

            {data && pending.length === 0 && (
              <EmptyState icon={ShieldCheckIcon}>
                {filtered && data.pending.length > 0
                  ? `No active safety overrides for patient: ${selected}.`
                  : "All prescription requests safe. No active safety overrides pending review."}
              </EmptyState>
            )}

            {pending.map((alert) => (
              <AlertCard
                key={alert.session_id}
                alert={alert}
                patients={data?.patients ?? {}}
                resolving={resolving[alert.session_id]}
                onResolve={(sessionId, decision) => void resolveAlert(sessionId, decision)}
                onLocate={onLocate}
              />
            ))}
          </div>

          <div className="flex flex-col gap-2 rounded-3xl bg-card p-3 shadow-card" aria-busy={isLoading}>
            <div className="flex flex-wrap items-center justify-between gap-2 px-2 pt-1">
              <h3 id="decisions-heading" tabIndex={-1} className="font-heading text-xl font-medium tracking-tight">
                Past Override Decisions
              </h3>
              <Button
                variant="outline"
                size="touch"
                disabled={!data}
                onClick={() => downloadAuditLog(data?.resolved ?? [])}
              >
                <DownloadIcon aria-hidden data-icon="inline-start" />
                Export Audit (CSV)
              </Button>
            </div>

            {isLoading && (
              <div role="status" className="px-2 pb-2">
                <span className="sr-only">Loading past decisions…</span>
                <Skeleton className="h-24 rounded-2xl" />
              </div>
            )}

            {data && resolved.length === 0 && (
              <p className="px-4 py-6 text-center text-muted-foreground">
                {filtered && data.resolved.length > 0
                  ? `No past decisions logged for patient: ${selected}.`
                  : "No past decisions logged in this session."}
              </p>
            )}

            {resolved.length > 0 && <DecisionsTable decisions={resolved} onLocate={onLocate} />}
          </div>
        </>
      )}

      {loadError && data && (
        <PanelError title="The latest data could not be loaded" message={loadError} onRetry={() => void refresh()} />
      )}
    </section>
  );
}
