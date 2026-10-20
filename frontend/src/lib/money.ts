// Money is a decimal STRING everywhere ("1500.50"), exactly as the API sends it. It is never
// turned into a JS number for arithmetic: floats cannot represent most cents exactly.
// Display formatting and comparisons work on the digits (or on BigInt cents) instead.

const MONEY = /^\d+(\.\d{1,2})?$/;

/** "1500.5" -> 150050n. Exact: no floating point involved. */
export function toCents(value: string): bigint {
  const negative = value.startsWith("-");
  const [whole, fraction = ""] = value.replace("-", "").split(".");
  const cents = BigInt(whole || "0") * 100n + BigInt((fraction + "00").slice(0, 2));
  return negative ? -cents : cents;
}

/** 150050n -> "1500.50". */
export function fromCents(cents: bigint): string {
  const abs = cents < 0n ? -cents : cents;
  const fraction = (abs % 100n).toString().padStart(2, "0");
  return `${cents < 0n ? "-" : ""}${abs / 100n}.${fraction}`;
}

/** True for a positive amount with at most 2 decimals, e.g. "30", "30.5", "30.50". */
export function isValidAmount(value: string): boolean {
  return MONEY.test(value) && toCents(value) > 0n;
}

/** "1500.5" -> "1500.50". Normalises what the user typed before it is sent. */
export function normaliseAmount(value: string): string {
  return fromCents(toCents(value));
}

/** Indian digit grouping (12,34,567.50) with the rupee sign. Input is a decimal string.
 *  `trimZeroCents` drops a redundant ".00" (for tight spaces like headline cards); non-zero
 *  cents are always shown. */
export function formatInr(value: string, trimZeroCents = false): string {
  const cents = toCents(value);
  const [whole, fraction] = fromCents(cents < 0n ? -cents : cents).split(".");
  const last3 = whole.slice(-3);
  const rest = whole.slice(0, -3);
  const grouped = rest ? `${rest.replace(/\B(?=(\d{2})+(?!\d))/g, ",")},${last3}` : last3;
  const decimals = trimZeroCents && fraction === "00" ? "" : `.${fraction}`;
  return `${cents < 0n ? "-" : ""}₹${grouped}${decimals}`;
}

/** Whole-number percentage of `part` in `total` (both decimal strings), clamped to 0-100.
 *  For progress bars only: this is display maths, never stored or sent anywhere. */
export function percent(part: string, total: string): number {
  const t = toCents(total);
  if (t <= 0n) return 0;
  const p = (toCents(part) * 100n) / t;
  return Number(p < 0n ? 0n : p > 100n ? 100n : p);
}

/** Larger of two amounts, as a string. Used for sorting, never for display maths. */
export function compareMoney(a: string, b: string): number {
  const diff = toCents(a) - toCents(b);
  return diff === 0n ? 0 : diff < 0n ? -1 : 1;
}
