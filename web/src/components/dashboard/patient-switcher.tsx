"use client";

import { UserIcon, UsersIcon } from "lucide-react";

import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ALL_PATIENTS, patientLabel } from "@/lib/format";
import type { PatientFilter, Patients } from "@/lib/types";

/*
 * Patient picker built on the shadcn/ui Select, shaped like the pill search
 * field of the reference layout. The leading icon plus name-and-id rows follow
 * "Select with Avatar" by @felipemenezes098 on 21st.dev (visual reference).
 */
export function PatientSwitcher({
  patients,
  value,
  onChange,
  disabled,
}: {
  patients: Patients;
  value: PatientFilter;
  onChange: (value: PatientFilter) => void;
  disabled?: boolean;
}) {
  const items = [
    { value: ALL_PATIENTS, label: "All Patients" },
    ...Object.entries(patients).map(([id, patient]) => ({ value: id, label: patientLabel(id, patient) })),
  ];

  return (
    <Select
      items={items}
      value={value}
      disabled={disabled}
      onValueChange={(next) => {
        if (typeof next === "string") onChange(next);
      }}
    >
      <SelectTrigger
        aria-label="Patient view"
        className="w-full min-w-0 flex-1 rounded-full bg-card pr-3 pl-4 text-base shadow-card data-[size=default]:h-11 sm:w-72 sm:flex-none sm:text-sm"
      >
        <span className="flex min-w-0 items-center gap-2">
          {value === ALL_PATIENTS ? (
            <UsersIcon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          ) : (
            <UserIcon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          )}
          <SelectValue className="truncate" />
        </span>
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="start" className="rounded-2xl p-1">
        {items.map((item) => (
          <SelectItem key={item.value} value={item.value} className="min-h-11 rounded-xl text-base sm:text-sm">
            {item.value === ALL_PATIENTS ? (
              <UsersIcon aria-hidden className="size-4 text-muted-foreground" />
            ) : (
              <UserIcon aria-hidden className="size-4 text-muted-foreground" />
            )}
            {item.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
