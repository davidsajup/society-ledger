import { IconArrowBackUp, IconCoin, IconReceipt } from "@tabler/icons-react";
import type { ComponentType } from "react";

import type { LedgerEntry } from "../api/types";

export interface EntryLook {
  title: string;
  icon: ComponentType<{ size?: number }>;
  color: string;
  /** "+" raises what the flat owes, "−" lowers it. */
  sign: "+" | "−";
}

/** One place that decides how a ledger entry is worded and coloured, for every screen. */
export function describeEntry(entry: LedgerEntry): EntryLook {
  if (entry.reverses !== null) {
    return entry.kind === "charge"
      ? { title: "Payment reversed", icon: IconArrowBackUp, color: "orange", sign: "+" }
      : { title: "Charge cancelled", icon: IconArrowBackUp, color: "teal", sign: "−" };
  }
  return entry.kind === "charge"
    ? { title: "Maintenance due", icon: IconReceipt, color: "gray", sign: "+" }
    : { title: "Payment received", icon: IconCoin, color: "teal", sign: "−" };
}

const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** "Maintenance due, October 2026" when the note names the month; otherwise the plain title. */
export function entryHeading(entry: LedgerEntry, look: EntryLook): string {
  if (entry.reverses === null && entry.kind === "charge") {
    const cycle = friendlyNote(entry.note);
    if (cycle !== entry.note) {
      const named = cycle.replace(/^Maintenance\s*/, "");
      return named ? `${look.title}, ${named}` : look.title;
    }
  }
  return look.title;
}

/** Notes are written by the server ("Maintenance 2026-10"); show the month the way people say it. */
export function friendlyNote(note: string): string {
  return note
    .replace(/\b(\d{4})-Q([1-4])\b/g, (_, year: string, quarter: string) => {
      const first = (Number(quarter) - 1) * 3;
      return `${MONTHS[first].slice(0, 3)}\u2013${MONTHS[first + 2].slice(0, 3)} ${year}`;
    })
    .replace(/\b(\d{4})-(0[1-9]|1[0-2])\b/g, (_, year: string, month: string) => {
      return `${MONTHS[Number(month) - 1]} ${year}`;
    });
}
