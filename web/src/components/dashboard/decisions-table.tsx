"use client";

import { LocateFixedIcon } from "lucide-react";

import { DecisionBadge } from "@/components/dashboard/status-badges";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { medicationLabel } from "@/lib/format";
import type { SafetyAlert } from "@/lib/types";

// Headers may wrap so that all four columns fit a 375px screen without sideways scrolling.
const head =
  "h-9 px-1.5 align-bottom text-xs font-medium tracking-wide whitespace-normal text-muted-foreground uppercase sm:px-3";
const cell = "px-1.5 sm:px-3";

/*
 * Past override decisions in a shadcn/ui Table. The card-wrapped table with
 * status pills follows "Card Table" by @felipemenezes098 on 21st.dev (visual
 * reference). Columns match the audit CSV.
 */
export function DecisionsTable({
  decisions,
  onLocate,
}: {
  decisions: SafetyAlert[];
  onLocate: (sessionId: string) => void;
}) {
  return (
    <Table className="text-base">
      <TableCaption className="sr-only">Past override decisions</TableCaption>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className={head}>Patient ID</TableHead>
          <TableHead className={head}>Prescribed medication</TableHead>
          <TableHead className={head}>Caregiver action</TableHead>
          <TableHead className={`${head} w-px`}>
            <span className="sr-only">Locate</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {decisions.map((decision) => (
          <TableRow
            key={decision.session_id}
            onClick={() => onLocate(decision.session_id)}
            className="cursor-pointer hover:bg-muted"
          >
            <TableCell className={`${cell} font-medium break-words whitespace-normal`}>{decision.patient_id}</TableCell>
            <TableCell className={`${cell} break-words whitespace-normal`}>{medicationLabel(decision)}</TableCell>
            <TableCell className={cell}>
              <DecisionBadge status={decision.status} />
            </TableCell>
            <TableCell className="px-0 text-right sm:px-1">
              <Button
                variant="ghost"
                size="icon-touch"
                title="Locate in Sandbox"
                aria-label={`Locate ${medicationLabel(decision)} for patient ${decision.patient_id} in the sandbox`}
                onClick={(event) => {
                  event.stopPropagation();
                  onLocate(decision.session_id);
                }}
              >
                <LocateFixedIcon aria-hidden />
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
