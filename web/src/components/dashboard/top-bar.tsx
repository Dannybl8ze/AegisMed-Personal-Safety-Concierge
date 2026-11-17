"use client";

import { ShieldCheckIcon } from "lucide-react";

import { AddPatientDialog } from "@/components/dashboard/add-patient-dialog";
import { PatientSwitcher } from "@/components/dashboard/patient-switcher";
import { ResetDialog } from "@/components/dashboard/reset-dialog";
import { SignOutButton } from "@/components/dashboard/sign-out-button";
import type { Dashboard } from "@/hooks/use-dashboard";
import type { PatientFilter } from "@/lib/types";

/** Brand, patient switcher and Add Patient. On small screens it also carries Reset and Sign out. */
export function TopBar({
  dashboard,
  selected,
  onSelect,
  onSignOut,
}: {
  dashboard: Dashboard;
  selected: PatientFilter;
  onSelect: (value: PatientFilter) => void;
  /** Present only when the deployment asks people to sign in. */
  onSignOut?: () => void;
}) {
  const { data, addPatient, resetDemo } = dashboard;

  return (
    <header className="flex flex-wrap items-center gap-3 px-4 pt-4 sm:px-6 lg:pt-5 lg:pl-0">
      <div className="flex min-w-0 flex-1 basis-0 items-center gap-3">
        <span
          aria-hidden
          className="flex size-11 shrink-0 items-center justify-center rounded-full bg-card shadow-card lg:hidden"
        >
          <ShieldCheckIcon className="size-6" strokeWidth={1.75} />
        </span>
        <div className="min-w-0">
          <h1 className="font-heading text-2xl leading-tight font-semibold tracking-tight">AegisMed</h1>
          <p className="truncate text-sm text-muted-foreground">Personal Prescription Safety Concierge</p>
        </div>
      </div>

      <div className="order-last flex w-full items-center gap-2 sm:order-none sm:w-auto">
        <PatientSwitcher patients={data?.patients ?? {}} value={selected} onChange={onSelect} disabled={!data} />
        <AddPatientDialog onSubmit={addPatient} disabled={!data} />
      </div>

      <ResetDialog onReset={resetDemo} className="lg:hidden" />
      {onSignOut && <SignOutButton onSignOut={onSignOut} className="lg:hidden" />}
    </header>
  );
}
