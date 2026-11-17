"use client";

import { LogOutIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Ends the session. Only shown when the deployment asks people to sign in. */
export function SignOutButton({ onSignOut, className }: { onSignOut: () => void; className?: string }) {
  return (
    <Button
      variant="outline"
      size="icon-touch"
      title="Sign out"
      aria-label="Sign out"
      onClick={onSignOut}
      className={cn("shrink-0 shadow-card", className)}
    >
      <LogOutIcon aria-hidden />
    </Button>
  );
}
