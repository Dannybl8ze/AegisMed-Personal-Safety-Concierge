import { CircleCheckIcon, CircleXIcon } from "lucide-react";

import { cn } from "@/lib/utils";
import type { AlertStatus } from "@/lib/types";

const LEVELS = ["low", "medium", "high"] as const;

const METER_TONE: Record<(typeof LEVELS)[number], { bar: string; text: string }> = {
  low: { bar: "bg-meter-low", text: "text-success" },
  medium: { bar: "bg-meter-medium", text: "text-warning" },
  high: { bar: "bg-meter-high", text: "text-destructive" },
};

/**
 * Risk level as a three-step meter plus words. The number of filled steps and
 * the label carry the meaning, so it does not depend on colour.
 */
export function RiskMeter({ level, className }: { level: string; className?: string }) {
  const normalized = level.trim().toLowerCase();
  const index = LEVELS.indexOf(normalized as (typeof LEVELS)[number]);
  const tone = index >= 0 ? METER_TONE[LEVELS[index]] : { bar: "bg-meter-off", text: "text-muted-foreground" };

  return (
    <div className={cn("flex shrink-0 flex-col items-end gap-1.5", className)}>
      <div aria-hidden className="flex gap-1">
        {LEVELS.map((step, position) => (
          <span key={step} className={cn("h-2 w-7 rounded-full", position <= index ? tone.bar : "bg-meter-off")} />
        ))}
      </div>
      <span className={cn("text-xs font-semibold tracking-wide uppercase", tone.text)}>{level} risk</span>
    </div>
  );
}

/** The caregiver's recorded decision, as a pastel pill with an icon and a word. */
export function DecisionBadge({ status, className }: { status: AlertStatus; className?: string }) {
  const approved = status === "approved";
  const Icon = approved ? CircleCheckIcon : CircleXIcon;
  return (
    <span
      className={cn(
        "inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-sm font-medium capitalize",
        approved ? "bg-surface-success text-on-surface-success" : "bg-surface-danger text-on-surface-danger",
        className,
      )}
    >
      <Icon aria-hidden className="size-3.5" />
      {status}
    </span>
  );
}
