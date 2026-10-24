// Shapes of the Django API. Every `string` that holds money is a decimal string ("1500.50").

export type Role = "president" | "secretary" | "treasurer" | "resident";

export interface Membership {
  society_id: number;
  society_name: string;
  billing_cycle_months: number; // 1 = billed monthly, 3 = quarterly
  role: Role;
  flat_id: number | null;
  flat_label: string | null;
}

export interface Me {
  id: number;
  username: string;
  must_change_password: boolean;
  is_platform_admin: boolean; // the super admin: onboards societies, sees no money
  memberships: Membership[];
}

export interface LedgerEntry {
  id: number;
  flat: number;
  kind: "charge" | "payment";
  amount: string;
  note: string;
  reverses: number | null;
  recorded_by: string; // "system" for entries made by the billing job
  created_at: string;
}

export interface FlatLedger {
  flat: { id: number; label: string };
  outstanding: string;
  entries: LedgerEntry[];
}

export interface Totals {
  billed: string;
  collected: string;
  outstanding: string;
  spent: string;
}

export interface FlatBalance {
  id: number;
  label: string;
  billed: string;
  collected: string;
  outstanding: string;
}

export interface Summary {
  totals: Totals;
  flats: FlatBalance[];
}

export interface RecentPayment {
  id: number;
  flat_id: number;
  flat_label: string;
  amount: string;
  note: string;
  recorded_by: string;
  created_at: string;
  is_reversal: boolean;
  reversed: boolean;
}

export type ExpenseCategory = "utilities" | "repairs" | "salaries" | "security" | "other";

export interface Expense {
  id: number;
  category: ExpenseCategory;
  description: string;
  amount: string;
  paid_on: string;
  created_by: string;
  reverses: number | null;
  created_at: string;
}

export interface ExpenseList {
  total_spent: string;
  expenses: Expense[];
}

export interface Flat {
  id: number;
  label: string;
  maintenance_amount: string; // per billing cycle (a month or a quarter)
}

export type LoginStatus = "active" | "temporary" | "expired";

export interface Member {
  id: number;
  user: string; // username
  name: string;
  login_status: LoginStatus;
  role: Role;
  flat: number | null;
  phone: string; // contact details: shown to the president and secretary only
  email: string;
}

/** A society as the super admin sees it: counts and logins, never money. */
export interface PlatformManager {
  member_id: number;
  name: string;
  username: string;
  role: Role;
  login_status: LoginStatus;
}

/** What pressing "Remind flats that owe" would do right now. Counts only: never an address. */
export interface ReminderPreview {
  flats_owing: number;
  flats_cooling_down: number; // reminded in the last 7 days
  flats_without_email: number;
  flats_eligible: number;
  recipients: number; // emails that would go out
  batch_limit: number; // the most emails one press sends
}

export interface ReminderResult extends Omit<ReminderPreview, "batch_limit"> {
  flats_reminded: number;
  flats_deferred: number; // eligible, but left for the next press
  sent: number;
  failed: number;
}

export type ClaimMethod = "upi" | "bank" | "cash" | "cheque" | "other";
export type ClaimStatus = "pending" | "accepted" | "rejected" | "withdrawn";

/** A resident's note that their flat paid. It is not money until an office-bearer records it. */
export interface PaymentClaim {
  id: number;
  flat: number;
  flat_label: string;
  claimed_by_name: string;
  amount: string;
  paid_on: string; // a date, YYYY-MM-DD
  method: ClaimMethod;
  reference: string;
  status: ClaimStatus;
  resolution_note: string; // why it was rejected
  accepted_amount: string | null; // what was recorded, if it differs from `amount`
  ledger_entry_id: number | null;
  created_at: string;
  resolved_at: string | null;
}

/** How the society is billed, and whether that can still be changed. */
export interface BillingSettings {
  billing_cycle_months: number;
  billing_start: string | null;
  locked: boolean; // true once the first billing run exists
  flats_with_amounts: number;
}

export interface PlatformSociety {
  id: number;
  name: string;
  slug: string;
  created_at: string;
  billing_cycle_months: number;
  billing_start: string | null;
  flat_count: number;
  member_count: number;
  managers: PlatformManager[];
}

export interface CreatedSociety extends IssuedLogin {
  society: { id: number; name: string; slug: string };
  president_name: string;
}

/** The ONE response that carries a temporary password. It is never available again. */
export interface IssuedLogin {
  username: string;
  temp_password: string;
  expires_at: string;
  member?: Member;
}

export interface AuditRow {
  id: number;
  action:
    | "payment.recorded"
    | "entry.reversed"
    | "billing.run"
    | "expense.recorded"
    | "expense.reversed"
    | "member.created"
    | "credentials.reissued"
    | "member.updated";
  actor: string; // "system" for the billing job
  flat: number | null;
  object_type: string;
  object_id: number;
  amount: string | null;
  data: Record<string, unknown>;
  created_at: string;
}

export interface BillingRun {
  id: number;
  period: string; // first day of the billed month, "2026-10-01"
  flats_charged: number;
  total_amount: string;
  created_at: string;
}

export type DuesStatus = "paid" | "partial" | "unpaid" | "none";

export interface DuesCell {
  period: string;
  billed: string;
  paid: string;
  due: string;
  status: DuesStatus;
}

export interface DuesFlat {
  id: number;
  label: string;
  outstanding: string;
  cells: DuesCell[];
}

export interface Dues {
  cycle_months: number;
  periods: string[];
  flats: DuesFlat[];
  summary: { flats: number; flats_with_dues: number; oldest_unpaid: string | null };
}

export interface DemoAccount {
  username: string;
  role: Role;
  society_name: string;
  flat_label: string | null;
}

export interface DemoInfo {
  enabled: boolean;
  accounts: DemoAccount[];
}

// --- Bulk import (CSV or Excel) ---------------------------------------------------------------

export interface ImportRow {
  row: number; // the spreadsheet row, so a problem can be found in the file
  flat: string;
  name: string;
  phone: string;
  email: string;
  maintenance: string; // exact "4500.00", never a number
  role: Role;
}

export interface ImportProblem {
  row: number;
  field: string;
  message: string;
}

export interface ImportPreview {
  rows: ImportRow[];
  errors: ImportProblem[];
  ignored_columns: string[];
  summary: { flats: number; people: number; total_per_cycle: string };
  cycle_months: number;
}

/** One new person's login. The password exists only in this response. */
export interface ImportedLogin {
  name: string;
  flat: string;
  role: Role;
  username: string;
  temp_password: string;
  expires_at: string;
}

export interface ImportResult {
  flats: number;
  people: number;
  logins: ImportedLogin[];
}
