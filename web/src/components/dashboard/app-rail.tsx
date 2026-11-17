"use client";

import { useRef } from "react";
import { ShieldCheckIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/*
 * Adapted from "Rail Panel Sidebar" by @dhxwhy on 21st.dev (component 44858).
 * Kept: the icon rail with a brand slot, a footer slot, per-section badges,
 * aria-current on the active item and roving focus with the arrow keys.
 * Dropped: the context panel, pin/peek behaviour and search, which this
 * single-page dashboard has no use for. Restyled as a floating white pill.
 */

export type RailSection = {
  id: string;
  label: string;
  icon: React.ReactNode;
  /** Shown as a small counter on the icon when greater than zero. */
  badge?: number;
};

export function AppRail({
  sections,
  activeId,
  onSelect,
  footer,
  className,
}: {
  sections: RailSection[];
  activeId: string;
  onSelect: (id: string) => void;
  footer?: React.ReactNode;
  className?: string;
}) {
  const buttons = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKeyDown(event: React.KeyboardEvent) {
    const ids = sections.map((section) => section.id);
    const target = event.target instanceof HTMLElement ? event.target.dataset.sectionButton : undefined;
    const current = Math.max(0, ids.indexOf(target ?? activeId));
    let next = -1;
    if (event.key === "ArrowDown") next = (current + 1) % ids.length;
    else if (event.key === "ArrowUp") next = (current - 1 + ids.length) % ids.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = ids.length - 1;
    if (next < 0) return;
    event.preventDefault();
    buttons.current[ids[next]]?.focus();
  }

  return (
    <aside aria-label="Sidebar" className={cn("flex w-24 shrink-0 flex-col items-center gap-6 py-5", className)}>
      <div
        aria-hidden
        className="flex size-14 items-center justify-center rounded-full bg-card text-foreground shadow-card"
      >
        <ShieldCheckIcon className="size-7" strokeWidth={1.75} />
      </div>

      <nav aria-label="Sections" className="rounded-full bg-card p-2 shadow-card">
        <div role="list" onKeyDown={onKeyDown} className="flex flex-col items-center gap-1.5">
          {sections.map((section) => {
            const selected = section.id === activeId;
            const hasBadge = typeof section.badge === "number" && section.badge > 0;
            return (
              <div key={section.id} role="listitem" className="flex">
                <button
                  ref={(node) => {
                    buttons.current[section.id] = node;
                  }}
                  type="button"
                  data-section-button={section.id}
                  title={section.label}
                  aria-label={hasBadge ? `${section.label}, ${section.badge} pending` : section.label}
                  aria-current={selected ? "location" : undefined}
                  tabIndex={selected ? 0 : -1}
                  onClick={() => onSelect(section.id)}
                  className={cn(
                    "relative flex size-11 cursor-pointer items-center justify-center rounded-full transition-colors duration-200",
                    selected ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/70 hover:text-foreground",
                  )}
                >
                  <span aria-hidden className="[&>svg]:size-5">
                    {section.icon}
                  </span>
                  {hasBadge && (
                    <span
                      aria-hidden
                      className="absolute -top-0.5 -right-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary px-1 text-[11px] leading-none font-semibold text-primary-foreground tabular-nums"
                    >
                      {section.badge}
                    </span>
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </nav>

      {footer !== undefined && <div className="mt-auto flex flex-col items-center gap-2">{footer}</div>}
    </aside>
  );
}
