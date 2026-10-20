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
