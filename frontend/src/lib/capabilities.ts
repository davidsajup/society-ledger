import type { Role } from "../api/types";

/**
 * What each role may do. This MIRRORS apps/societies/roles.py and exists only to decide what to
 * show: the server checks every request, so a mismatch here can hide a button but never grant
 * access. Keep the two in step (the backend has a test that pins its table).
 */
export type Capability =
  | "viewAllBalances"
  | "recordPayment"
  | "reversePayment"
  | "recordExpense"
  | "manageFlats"
  | "manageMembers"
  | "viewBillingSettings"
  | "sendReminders"
  | "manageBilling";

const OFFICE_BEARER: Capability[] = [
  "viewAllBalances",
  "recordPayment",
  "reversePayment",
  "viewBillingSettings",
  "sendReminders",
];

const TABLE: Record<Role, ReadonlySet<Capability>> = {
  // Only the president decides how often the society is billed and when billing starts.
  president: new Set<Capability>([...OFFICE_BEARER, "manageFlats", "manageMembers", "manageBilling"]),
  secretary: new Set<Capability>([...OFFICE_BEARER, "manageFlats", "manageMembers"]),
  treasurer: new Set<Capability>([...OFFICE_BEARER, "recordExpense"]),
  resident: new Set<Capability>(),
};

export const can = (role: Role, capability: Capability): boolean => TABLE[role].has(capability);

/** President, secretary and treasurer: the people who run the society's books. */
export const isOfficeBearer = (role: Role): boolean => role !== "resident";

export const ROLE_LABEL: Record<Role, string> = {
  president: "President",
  secretary: "Secretary",
  treasurer: "Treasurer",
  resident: "Resident",
};

/** Roles in the order they are offered when creating or changing a member. */
export const ROLE_OPTIONS: { value: Role; label: string }[] = [
  { value: "resident", label: ROLE_LABEL.resident },
  { value: "treasurer", label: ROLE_LABEL.treasurer },
  { value: "secretary", label: ROLE_LABEL.secretary },
  { value: "president", label: ROLE_LABEL.president },
];
