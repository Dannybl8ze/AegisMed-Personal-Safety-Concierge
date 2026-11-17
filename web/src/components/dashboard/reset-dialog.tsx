"use client";

import { useState } from "react";
import { Loader2Icon, RotateCcwIcon } from "lucide-react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** "Reset Demo State" as a round icon button that asks for confirmation first. */
export function ResetDialog({ onReset, className }: { onReset: () => Promise<boolean>; className?: string }) {
  const [open, setOpen] = useState(false);
  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    setResetting(true);
    await onReset();
    setResetting(false);
    setOpen(false);
  }

  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger
        render={
          <Button
            variant="outline"
            size="icon-touch"
            title="Reset Demo State"
            aria-label="Reset Demo State"
            className={cn("shrink-0 shadow-card", className)}
          />
        }
      >
        <RotateCcwIcon aria-hidden />
      </AlertDialogTrigger>
      <AlertDialogContent className="rounded-3xl">
        <AlertDialogHeader>
          <AlertDialogTitle className="text-xl">Reset the chat logs and agent memory?</AlertDialogTitle>
          <AlertDialogDescription className="text-base">
            This clears the chat history, the active alerts and the past override decisions. Registered patients are
            kept.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter className="rounded-b-3xl">
          <AlertDialogCancel size="touch" disabled={resetting}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction size="touch" disabled={resetting} onClick={() => void handleReset()}>
            {resetting && <Loader2Icon aria-hidden data-icon="inline-start" className="animate-spin" />}
            {resetting ? "Resetting…" : "Reset Demo State"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
