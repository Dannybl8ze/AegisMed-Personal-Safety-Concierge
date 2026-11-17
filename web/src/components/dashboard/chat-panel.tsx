"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2Icon, PillIcon, SendIcon } from "lucide-react";

import { MessageBubble } from "@/components/dashboard/message-bubble";
import { PanelError } from "@/components/dashboard/panel-states";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import type { Dashboard } from "@/hooks/use-dashboard";
import {
  ALL_PATIENTS,
  allergySummary,
  findPatient,
  initials,
  matchesPatient,
  messageTime,
  patientLabel,
  stripLeadingEmoji,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import type { ChatMessage, Patient, PatientFilter, Patients } from "@/lib/types";

const WELCOME = "Hello! I am your AegisMed safety concierge. What medication would you like to add or schedule today?";

function PatientBanner({ patient }: { patient: Patient }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 rounded-2xl bg-muted px-4 py-3">
      <div className="flex min-w-0 items-center gap-3">
        <div
          aria-hidden
          className="flex size-11 shrink-0 items-center justify-center rounded-full bg-primary font-heading text-sm font-semibold text-primary-foreground"
        >
          {initials(patient.name)}
        </div>
        <div className="min-w-0">
          <p className="font-heading text-lg leading-tight font-semibold break-words">{patient.name}</p>
          <p className="text-sm text-muted-foreground break-words">
            Age: {patient.age} <span aria-hidden>|</span> Allergies: {allergySummary(patient)}
          </p>
        </div>
      </div>
      <div className="min-w-0 sm:text-right">
        <p className="text-sm text-muted-foreground">Active Regimen</p>
        <p className="flex items-center gap-1.5 font-semibold break-words sm:justify-end">
          <PillIcon aria-hidden className="size-4 shrink-0 text-muted-foreground" />
          {patient.active}
        </p>
      </div>
    </div>
  );
}

function tagFor(patients: Patients, patientId: string | undefined, selected: PatientFilter): string | undefined {
  if (selected !== ALL_PATIENTS) return undefined;
  const patient = findPatient(patients, patientId);
  return patient && patientId ? patientLabel(patientId, patient) : undefined;
}

function historyBubble(message: ChatMessage, index: number, patients: Patients, selected: PatientFilter, located: string | null) {
  const held = message.sender === "agent" && message.status === "paused";
  return (
    <MessageBubble
      key={`${message.session_id}-${index}`}
      variant={message.sender}
      state={held ? "held" : "default"}
      text={held ? stripLeadingEmoji(message.text) : message.text}
      time={messageTime(message)}
      patientTag={tagFor(patients, message.patient_id, selected)}
      sessionId={message.session_id}
      highlighted={Boolean(located) && message.session_id === located}
    />
  );
}

export function ChatPanel({
  dashboard,
  selected,
  located,
  className,
}: {
  dashboard: Dashboard;
  selected: PatientFilter;
  located: string | null;
  className?: string;
}) {
  const { data, loadError, isLoading, pendingChat, chatFailure, sessionId, sendMessage, refresh } = dashboard;
  const [draft, setDraft] = useState("");
  const logRef = useRef<HTMLDivElement>(null);

  const patients = data?.patients ?? {};
  const history = (data?.history ?? []).filter((m) => matchesPatient(selected, m.patient_id, { includeUnknown: true }));
  const selectedPatient = selected === ALL_PATIENTS ? undefined : patients[selected];
  const showPending = pendingChat && matchesPatient(selected, pendingChat.patientId, { includeUnknown: true });
  const showFailure = chatFailure && matchesPatient(selected, chatFailure.patientId, { includeUnknown: true });
  const sending = pendingChat !== null;

  // Keep the newest message in view.
  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [history.length, sending, showFailure, selected]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = draft;
    if (!text.trim()) return;
    setDraft("");
    const sent = await sendMessage(text, selected);
    if (!sent) setDraft(text);
  }

  return (
    <section
      id="sandbox"
      aria-labelledby="chat-heading"
      className={cn("flex flex-col gap-4 rounded-3xl bg-card p-4 shadow-card sm:p-6", className)}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h2 id="chat-heading" className="font-heading text-2xl font-medium tracking-tight">
          Patient Assistant Sandbox
        </h2>
        <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
          <span aria-hidden className={cn("size-2 rounded-full", loadError ? "bg-destructive" : "bg-meter-low")} />
          {loadError ? "Offline" : "Online"} <span aria-hidden>·</span> Session ID: {sessionId}
        </p>
      </div>

      {selectedPatient && <PatientBanner patient={selectedPatient} />}

      <div
        ref={logRef}
        role="log"
        aria-label="Conversation"
        aria-busy={isLoading || sending}
        tabIndex={0}
        className="flex h-[55dvh] min-h-80 flex-col gap-4 overflow-y-auto rounded-2xl bg-muted p-4 lg:h-auto lg:min-h-0 lg:flex-1"
      >
        <MessageBubble variant="system" text={WELCOME} />

        {isLoading && (
          <div role="status" className="flex flex-col gap-4">
            <span className="sr-only">Loading the conversation…</span>
            <Skeleton className="ml-auto h-14 w-3/5 rounded-2xl bg-card" />
            <Skeleton className="h-16 w-4/5 rounded-2xl bg-card" />
            <Skeleton className="ml-auto h-14 w-1/2 rounded-2xl bg-card" />
          </div>
        )}

        {loadError && !data && (
          <PanelError title="The conversation could not be loaded" message={loadError} onRetry={() => void refresh()} />
        )}

        {history.map((message, index) => historyBubble(message, index, patients, selected, located))}

        {data && history.length === 0 && !showPending && !showFailure && selected !== ALL_PATIENTS && (
          <p className="text-center text-sm text-muted-foreground">No messages for this patient yet.</p>
        )}

        {showPending && (
          <>
            <MessageBubble
              variant="user"
              text={pendingChat.text}
              sessionId={pendingChat.sessionId}
              patientTag={tagFor(patients, pendingChat.patientId, selected)}
            />
            <MessageBubble variant="agent" state="pending" text="AegisMed is checking safety guidelines…" />
          </>
        )}

        {showFailure && (
          <>
            <MessageBubble variant="user" text={chatFailure.text} />
            <MessageBubble
              variant="agent"
              state="failed"
              text={`The safety check could not be completed. ${chatFailure.reason}`}
            />
          </>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2">
        <label htmlFor="chat-input" className="sr-only">
          Medication request
        </label>
        <Input
          id="chat-input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Try adding medication, e.g., 'Add Warfarin 6mg twice daily'..."
          autoComplete="off"
          required
          disabled={!data}
          className="h-11 flex-1 rounded-full px-4"
        />
        <Button type="submit" size="touch" disabled={!data || sending} className="shrink-0">
          {sending ? (
            <Loader2Icon aria-hidden data-icon="inline-start" className="animate-spin" />
          ) : (
            <SendIcon aria-hidden data-icon="inline-start" />
          )}
          {sending ? "Sending…" : "Send"}
        </Button>
      </form>
    </section>
  );
}
