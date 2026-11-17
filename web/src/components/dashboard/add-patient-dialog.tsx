"use client";

import { useId, useRef, useState } from "react";
import { Loader2Icon, UserPlusIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { NewPatient } from "@/lib/types";

type FieldName = keyof NewPatient;
type FieldErrors = Partial<Record<FieldName, string>>;

const FIELDS: { name: FieldName; label: string; placeholder: string; hint?: string; inputMode?: "numeric" }[] = [
  { name: "patient_id", label: "Patient ID", placeholder: "patient-105", hint: "A unique slug, for example patient-105." },
  { name: "name", label: "Full name", placeholder: "David Miller" },
  { name: "age", label: "Age", placeholder: "53", inputMode: "numeric" },
  { name: "allergies", label: "Allergies", placeholder: "metformin, penicillin", hint: "Optional. Separate with commas." },
  { name: "active", label: "Active medication regimen", placeholder: "Insulin Glargine 10 units" },
];

function validate(values: NewPatient): FieldErrors {
  const errors: FieldErrors = {};
  if (!values.patient_id.trim()) errors.patient_id = "Enter a patient ID.";
  if (!values.name.trim()) errors.name = "Enter the patient's full name.";
  const age = Number(values.age);
  if (!values.age.trim() || !Number.isInteger(age) || age < 0 || age > 130) {
    errors.age = "Enter an age between 0 and 130.";
  }
  if (!values.active.trim()) errors.active = "Enter the active regimen, or None.";
  return errors;
}

/*
 * Register-patient form in a shadcn/ui Dialog. Structure (header, labelled
 * fields, footer actions) follows "Dialog" by @wensity on 21st.dev, used as a
 * visual reference only.
 */
export function AddPatientDialog({
  onSubmit,
  disabled,
}: {
  onSubmit: (patient: NewPatient) => Promise<boolean>;
  disabled?: boolean;
}) {
  const formId = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const [open, setOpen] = useState(false);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [saving, setSaving] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const values = Object.fromEntries(FIELDS.map((f) => [f.name, String(form.get(f.name) ?? "")])) as NewPatient;

    const found = validate(values);
    setErrors(found);
    const firstInvalid = FIELDS.find((f) => found[f.name]);
    if (firstInvalid) {
      formRef.current?.querySelector<HTMLInputElement>(`[name="${firstInvalid.name}"]`)?.focus();
      return;
    }

    setSaving(true);
    const saved = await onSubmit(values);
    setSaving(false);
    if (saved) setOpen(false);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) setErrors({});
      }}
    >
      <DialogTrigger render={<Button size="touch" disabled={disabled} className="shrink-0" />}>
        <UserPlusIcon aria-hidden data-icon="inline-start" />
        Add Patient
      </DialogTrigger>

      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-3xl p-5 sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-2xl font-medium tracking-tight">Register new patient</DialogTitle>
          <DialogDescription>
            The patient appears in the switcher straight away and their allergies are checked on every request.
          </DialogDescription>
        </DialogHeader>

        <form ref={formRef} id={formId} noValidate onSubmit={handleSubmit} className="grid gap-4">
          {FIELDS.map((field) => {
            const inputId = `${formId}-${field.name}`;
            const error = errors[field.name];
            const describedBy = [field.hint && `${inputId}-hint`, error && `${inputId}-error`].filter(Boolean).join(" ");
            return (
              <div key={field.name} className="grid gap-1.5">
                <Label htmlFor={inputId}>{field.label}</Label>
                <Input
                  id={inputId}
                  name={field.name}
                  placeholder={field.placeholder}
                  inputMode={field.inputMode}
                  autoComplete="off"
                  aria-invalid={error ? true : undefined}
                  aria-describedby={describedBy || undefined}
                  className="h-11 rounded-xl px-3.5"
                />
                {field.hint && (
                  <p id={`${inputId}-hint`} className="text-sm text-muted-foreground">
                    {field.hint}
                  </p>
                )}
                {error && (
                  <p id={`${inputId}-error`} role="alert" className="text-sm font-medium text-destructive">
                    {error}
                  </p>
                )}
              </div>
            );
          })}
        </form>

        <DialogFooter className="-mx-5 -mb-5 rounded-b-3xl px-5">
          <DialogClose render={<Button variant="outline" size="touch" disabled={saving} />}>Cancel</DialogClose>
          <Button type="submit" form={formId} size="touch" disabled={saving}>
            {saving && <Loader2Icon aria-hidden data-icon="inline-start" className="animate-spin" />}
            {saving ? "Saving…" : "Save Patient"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
