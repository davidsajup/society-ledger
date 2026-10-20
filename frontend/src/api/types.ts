// Shapes of the Django API. Every `string` that holds money is a decimal string ("1500.50").

export type Role = "admin" | "treasurer" | "resident";

export interface Membership {
  society_id: number;
  society_name: string;
  role: Role;
  flat_id: number | null;
  flat_label: string | null;
}

export interface Me {
  id: number;
  username: string;
  memberships: Membership[];
}

export interface LedgerEntry {
  id: number;
  flat: number;
  kind: "charge" | "payment";
  amount: string;
  note: string;
  reverses: number | null;
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
  monthly_maintenance: string;
}

export interface Member {
  id: number;
  user: string;
  role: Role;
  flat: number | null;
}
