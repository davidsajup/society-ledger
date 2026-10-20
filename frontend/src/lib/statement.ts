import type { LedgerEntry } from "../api/types";
import { fromCents, toCents } from "./money";

export interface StatementRow {
  entry: LedgerEntry;
  /** What the flat owed immediately AFTER this entry. */
  balanceAfter: string;
  /** True if a later entry reverses this one. */
  reversed: boolean;
  /** A real payment (not a reversal marker): the kind of entry that gets a receipt. */
  isReceiptable: boolean;
}

/** How an entry moves the amount owed: charges raise it, payments lower it. */
function effect(entry: LedgerEntry): bigint {
  const cents = toCents(entry.amount);
  return entry.kind === "charge" ? cents : -cents;
}

/**
 * Turn the API's newest-first entries into statement rows with a running balance.
 *
 * The balance is computed BACKWARDS from the flat's current outstanding amount, which the
 * server calculated from the whole ledger. The list can be truncated (the API returns the
 * newest 200), so counting forwards from zero would be wrong; counting back from a known
 * truth is exact however many older entries exist.
 */
export function buildStatement(entries: LedgerEntry[], outstanding: string): StatementRow[] {
  const reversedIds = new Set(entries.map((e) => e.reverses).filter((id) => id !== null));
  let balance = toCents(outstanding);

  return entries.map((entry) => {
    const row: StatementRow = {
      entry,
      balanceAfter: fromCents(balance),
      reversed: reversedIds.has(entry.id),
      isReceiptable: entry.kind === "payment" && entry.reverses === null,
    };
    balance -= effect(entry); // step back to what it was before this entry
    return row;
  });
}

/** "R-000123": a stable, human-readable receipt number derived from the ledger entry id. */
export function receiptNumber(entryId: number): string {
  return `R-${String(entryId).padStart(6, "0")}`;
}
