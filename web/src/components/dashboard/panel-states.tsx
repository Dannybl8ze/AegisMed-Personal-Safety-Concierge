import type { LucideIcon } from "lucide-react";
import { OctagonXIcon, RefreshCwIcon } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Shown when a panel's data could not be loaded. */
export function PanelError({
  title,
  message,
  onRetry,
  className,
}: {
  title: string;
  message: string;
  onRetry: () => void;
  className?: string;
}) {
  return (
    <Alert className={cn("gap-x-3 rounded-2xl border-0 bg-surface-danger p-4", className)}>
      <OctagonXIcon aria-hidden className="size-5 text-destructive" />
      <AlertTitle className="text-base text-on-surface-danger">{title}</AlertTitle>
      <AlertDescription className="grid gap-3 text-base text-on-surface-danger">
        <p>{message}</p>
        <Button variant="outline" size="touch" className="w-fit" onClick={onRetry}>
          <RefreshCwIcon aria-hidden data-icon="inline-start" />
          Try again
        </Button>
      </AlertDescription>
    </Alert>
  );
}

/** Shown when a panel has loaded but has nothing to list. */
export function EmptyState({
  icon: Icon,
  children,
  className,
}: {
  icon: LucideIcon;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center gap-3 rounded-3xl bg-card px-6 py-8 text-center text-muted-foreground shadow-card",
        className,
      )}
    >
      <span aria-hidden className="flex size-11 items-center justify-center rounded-full bg-surface-success text-success">
        <Icon className="size-5" />
      </span>
      <p className="max-w-prose text-pretty">{children}</p>
    </div>
  );
}
