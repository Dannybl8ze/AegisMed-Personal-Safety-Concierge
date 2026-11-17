import {
  ClipboardCheckIcon,
  Loader2Icon,
  OctagonXIcon,
  ShieldCheckIcon,
  TriangleAlertIcon,
  UserIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";

/*
 * Adapted from "AI Message Bubble" by @elements- on 21st.dev (component 20125):
 * a role-based bubble with an avatar, a timestamp and an accessible article
 * wrapper. Provider logos, the copy button and the monospace type were dropped;
 * caregiver, held, failed and pending states were added.
 */

export type BubbleVariant = "user" | "agent" | "caregiver" | "system";
export type BubbleState = "default" | "held" | "failed" | "pending";

const SENDER_LABEL: Record<BubbleVariant, string> = {
  user: "Patient request",
  agent: "AegisMed response",
  caregiver: "Caregiver decision",
  system: "System message",
};

function Avatar({ variant, state }: { variant: BubbleVariant; state: BubbleState }) {
  const Icon =
    state === "failed"
      ? OctagonXIcon
      : state === "held"
        ? TriangleAlertIcon
        : variant === "user"
          ? UserIcon
          : variant === "caregiver"
            ? ClipboardCheckIcon
            : ShieldCheckIcon;
  return (
    <div
      aria-hidden
      className={cn(
        "flex size-9 shrink-0 items-center justify-center rounded-full",
        variant === "user" && "bg-primary text-primary-foreground",
        variant !== "user" && "bg-card text-foreground",
        variant === "caregiver" && "bg-surface-info text-info",
        state === "held" && "bg-surface-warning text-warning",
        state === "failed" && "bg-surface-danger text-destructive",
      )}
    >
      <Icon className="size-4" />
    </div>
  );
}

export function MessageBubble({
  variant,
  state = "default",
  text,
  time,
  patientTag,
  sessionId,
  highlighted = false,
  className,
}: {
  variant: BubbleVariant;
  state?: BubbleState;
  text: string;
  time?: string;
  patientTag?: string;
  sessionId?: string;
  highlighted?: boolean;
  className?: string;
}) {
  const isUser = variant === "user";
  const stateLabel =
    state === "held" ? "Held for caregiver review" : state === "failed" ? "Not completed" : undefined;

  return (
    <div
      data-slot="message-bubble"
      data-session-id={sessionId}
      role="article"
      aria-label={[SENDER_LABEL[variant], stateLabel, patientTag].filter(Boolean).join(", ")}
      tabIndex={-1}
      className={cn(
        "group flex scroll-my-6 gap-2.5 rounded-2xl outline-offset-4",
        isUser && "flex-row-reverse",
        variant === "caregiver" && "justify-center",
        className,
      )}
    >
      <Avatar variant={variant} state={state} />

      <div
        className={cn(
          "relative max-w-[85%] min-w-0 rounded-2xl px-4 py-3",
          isUser && "rounded-br-md bg-primary text-primary-foreground",
          (variant === "agent" || variant === "system") && "rounded-bl-md bg-card text-card-foreground",
          variant === "caregiver" && "bg-surface-info text-on-surface-info",
          state === "held" && "bg-surface-warning text-on-surface-warning",
          state === "failed" && "bg-surface-danger text-on-surface-danger",
          highlighted && "ring-3 ring-ring motion-safe:animate-locate",
        )}
      >
        <div
          className={cn(
            "mb-1 flex flex-wrap items-center gap-x-1.5 text-xs font-medium",
            isUser ? "text-primary-foreground/80" : "opacity-80",
          )}
        >
          {stateLabel && (
            <span className="inline-flex items-center gap-1 font-semibold tracking-wide uppercase">
              {stateLabel}
              <span aria-hidden>•</span>
            </span>
          )}
          {patientTag && (
            <>
              <span>{patientTag}</span>
              <span aria-hidden>•</span>
            </>
          )}
          {variant === "system" ? <span>System</span> : time ? <time>{time}</time> : null}
        </div>

        {state === "pending" ? (
          <p role="status" className="m-0 flex items-center gap-2 text-base leading-relaxed">
            <Loader2Icon aria-hidden className="size-4 shrink-0 animate-spin" />
            {text}
          </p>
        ) : (
          <p className="m-0 text-base leading-relaxed break-words whitespace-pre-wrap">{text}</p>
        )}
      </div>
    </div>
  );
}
