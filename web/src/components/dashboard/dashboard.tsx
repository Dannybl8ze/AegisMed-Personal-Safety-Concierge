"use client";

import { useRef, useState } from "react";
import { ClipboardListIcon, MessagesSquareIcon, ShieldAlertIcon } from "lucide-react";
import { toast } from "sonner";

import { AppRail, type RailSection } from "@/components/dashboard/app-rail";
import { ChatPanel } from "@/components/dashboard/chat-panel";
import { PanelError } from "@/components/dashboard/panel-states";
import { ResetDialog } from "@/components/dashboard/reset-dialog";
import { ReviewPortal } from "@/components/dashboard/review-portal";
import { SignIn } from "@/components/dashboard/sign-in";
import { SignOutButton } from "@/components/dashboard/sign-out-button";
import { TopBar } from "@/components/dashboard/top-bar";
import { useAuth } from "@/hooks/use-auth";
import { useDashboard, useHydrated } from "@/hooks/use-dashboard";
import { ALL_PATIENTS, matchesPatient } from "@/lib/format";
import type { PatientFilter } from "@/lib/types";

const HIGHLIGHT_MS = 2400;

/** Where each rail item takes the user. */
const SECTION_TARGET: Record<string, string> = {
  sandbox: "chat-input",
  alerts: "alerts-heading",
  decisions: "decisions-heading",
};

function prefersReducedMotion(): boolean {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function DashboardClient({
  signInRequired,
  onSignOut,
  onSignedOut,
}: {
  signInRequired: boolean;
  onSignOut: () => void;
  onSignedOut: () => void;
}) {
  const dashboard = useDashboard(onSignedOut);
  const [selected, setSelected] = useState<PatientFilter>(ALL_PATIENTS);
  const [located, setLocated] = useState<string | null>(null);
  const [section, setSection] = useState("sandbox");
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // A registered patient can disappear only if the store is replaced; fall back to "all".
  const selectedExists = selected === ALL_PATIENTS || !dashboard.data || selected in dashboard.data.patients;
  const activeFilter = selectedExists ? selected : ALL_PATIENTS;
  const pendingCount = (dashboard.data?.pending ?? []).filter((a) => matchesPatient(activeFilter, a.patient_id)).length;

  const sections: RailSection[] = [
    { id: "sandbox", label: "Patient Assistant Sandbox", icon: <MessagesSquareIcon /> },
    { id: "alerts", label: "Active alerts", icon: <ShieldAlertIcon />, badge: pendingCount },
    { id: "decisions", label: "Past override decisions", icon: <ClipboardListIcon /> },
  ];

  /** Rail navigation: bring a section into view and move focus to it. */
  function goToSection(id: string) {
    setSection(id);
    const target = document.getElementById(SECTION_TARGET[id]);
    if (!target) return;
    target.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" });
    target.focus({ preventScroll: true });
  }

  /** Scroll to the chat message behind an alert or decision and highlight it. */
  function locate(sessionId: string) {
    const target = document.querySelector<HTMLElement>(
      `[data-slot="message-bubble"][data-session-id="${CSS.escape(sessionId)}"]`,
    );
    if (!target) {
      toast.info("No chat message was found for this request.");
      return;
    }
    // Jump straight there: the highlight is timed, so it must not wait on a scroll animation.
    target.scrollIntoView({ behavior: "auto", block: "center" });
    target.focus({ preventScroll: true });

    setLocated(sessionId);
    if (highlightTimer.current) clearTimeout(highlightTimer.current);
    highlightTimer.current = setTimeout(() => setLocated(null), HIGHLIGHT_MS);
  }

  return (
    <div className="flex min-h-dvh lg:h-dvh">
      <a
        href="#chat-input"
        className="sr-only z-30 rounded-full bg-primary px-5 py-3 font-semibold text-primary-foreground focus:not-sr-only focus:absolute focus:top-3 focus:left-3"
      >
        Skip to medication request
      </a>

      <AppRail
        sections={sections}
        activeId={section}
        onSelect={goToSection}
        footer={
          <>
            <ResetDialog onReset={dashboard.resetDemo} />
            {signInRequired && <SignOutButton onSignOut={onSignOut} />}
          </>
        }
        className="hidden lg:flex"
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar
          dashboard={dashboard}
          selected={activeFilter}
          onSelect={setSelected}
          onSignOut={signInRequired ? onSignOut : undefined}
        />
        <main className="grid flex-1 grid-cols-1 gap-5 p-4 sm:p-6 lg:min-h-0 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:pl-0">
          <ChatPanel dashboard={dashboard} selected={activeFilter} located={located} className="lg:min-h-0" />
          <ReviewPortal
            dashboard={dashboard}
            selected={activeFilter}
            onLocate={locate}
            className="lg:-m-2 lg:min-h-0 lg:overflow-y-auto lg:p-2"
          />
        </main>
      </div>
    </div>
  );
}

/** Rendered on the server and during hydration, before any data can exist. */
function DashboardShell() {
  return (
    <div className="flex min-h-dvh flex-col gap-2 p-6">
      <p className="font-heading text-2xl font-semibold tracking-tight">AegisMed</p>
      <p className="text-sm text-muted-foreground">Personal Prescription Safety Concierge</p>
      <p role="status" className="mt-6 text-muted-foreground">
        Loading the caregiver dashboard…
      </p>
    </div>
  );
}

export function Dashboard() {
  const hydrated = useHydrated();
  const { state, signIn, signOut, expire, retry } = useAuth();

  if (!hydrated || state.phase === "checking") return <DashboardShell />;

  if (state.phase === "unreachable") {
    return (
      <main className="mx-auto flex min-h-dvh max-w-md items-center p-4">
        <PanelError
          className="w-full"
          title="The dashboard could not be reached"
          message={state.message}
          onRetry={retry}
        />
      </main>
    );
  }

  if (state.phase === "signed-out") return <SignIn configured={state.configured} onSignIn={signIn} />;

  return (
    <DashboardClient
      signInRequired={state.required}
      onSignOut={() => void signOut()}
      onSignedOut={expire}
    />
  );
}
