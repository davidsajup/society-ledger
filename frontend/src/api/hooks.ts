import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ApiError, api, forgetCsrfToken } from "./client";
import type {
  AuditRow,
  BillingRun,
  DemoInfo,
  Dues,
  ExpenseCategory,
  ExpenseList,
  Flat,
  FlatLedger,
  CreatedSociety,
  IssuedLogin,
  LedgerEntry,
  Me,
  Member,
  PlatformSociety,
  RecentPayment,
  Role,
  Summary,
} from "./types";

const base = (societyId: number) => `/societies/${societyId}`;

// Query keys always start with the society id, so one tenant's cache can never be shown for
// another and a whole tenant can be dropped at once.
export const keys = {
  me: ["me"] as const,
  demo: ["demo"] as const,
  ledger: (s: number, flatId: number) => ["ledger", s, flatId] as const,
  summary: (s: number) => ["summary", s] as const,
  activity: (s: number) => ["activity", s] as const,
  expenses: (s: number) => ["expenses", s] as const,
  dues: (s: number) => ["dues", s] as const,
  audit: (s: number) => ["audit", s] as const,
  billingRuns: (s: number) => ["billing-runs", s] as const,
  flats: (s: number) => ["flats", s] as const,
  members: (s: number) => ["members", s] as const,
  platformSocieties: ["platform-societies"] as const,
};

// --- Session -----------------------------------------------------------------------------

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: async (): Promise<Me | null> => {
      try {
        return await api<Me>("/auth/me/");
      } catch (error) {
        if (error instanceof ApiError && error.status === 403) return null; // not logged in
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

/** Is demo mode on, and which one-click accounts exist? Any failure just means "not a demo". */
export function useDemo() {
  return useQuery({
    queryKey: keys.demo,
    queryFn: async (): Promise<DemoInfo> => {
      try {
        return await api<DemoInfo>("/auth/demo/");
      } catch {
        return { enabled: false, accounts: [] };
      }
    },
    staleTime: 5 * 60_000,
  });
}

export function useDemoLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (username: string) =>
      api<Me>("/auth/demo-login/", { method: "POST", body: { username } }),
    onSuccess: (me) => {
      const demo = queryClient.getQueryData<DemoInfo>(keys.demo);
      forgetCsrfToken(); // Django rotates the CSRF token on login
      queryClient.clear();
      queryClient.setQueryData(keys.me, me);
      if (demo) queryClient.setQueryData(keys.demo, demo); // keep the banner's data
    },
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      api<Me>("/auth/login/", { method: "POST", body: credentials }),
    onSuccess: (me) => {
      forgetCsrfToken(); // Django rotates the CSRF token on login
      queryClient.clear();
      queryClient.setQueryData(keys.me, me);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api<null>("/auth/logout/", { method: "POST" }),
    onSuccess: () => {
      forgetCsrfToken();
      queryClient.clear(); // nothing from this session may survive into the next login
      queryClient.setQueryData(keys.me, null);
    },
  });
}

// --- Reads ---------------------------------------------------------------------------------

export function useLedger(societyId: number, flatId: number | null) {
  return useQuery({
    queryKey: keys.ledger(societyId, flatId ?? 0),
    queryFn: () => api<FlatLedger>(`${base(societyId)}/flats/${flatId}/ledger/`),
    enabled: flatId !== null,
  });
}

export function useSummary(societyId: number) {
  return useQuery({
    queryKey: keys.summary(societyId),
    queryFn: () => api<Summary>(`${base(societyId)}/summary/`),
  });
}

export function useActivity(societyId: number) {
  return useQuery({
    queryKey: keys.activity(societyId),
    queryFn: () => api<RecentPayment[]>(`${base(societyId)}/activity/`),
  });
}

export function useDues(societyId: number) {
  return useQuery({
    queryKey: keys.dues(societyId),
    queryFn: () => api<Dues>(`${base(societyId)}/dues/`),
  });
}

export function useAudit(societyId: number) {
  return useQuery({
    queryKey: keys.audit(societyId),
    queryFn: () => api<AuditRow[]>(`${base(societyId)}/audit/`),
  });
}

export function useBillingRuns(societyId: number) {
  return useQuery({
    queryKey: keys.billingRuns(societyId),
    queryFn: () => api<BillingRun[]>(`${base(societyId)}/billing-runs/`),
  });
}

export function useExpenses(societyId: number) {
  return useQuery({
    queryKey: keys.expenses(societyId),
    queryFn: () => api<ExpenseList>(`${base(societyId)}/expenses/`),
  });
}

export function useFlats(societyId: number) {
  return useQuery({
    queryKey: keys.flats(societyId),
    queryFn: () => api<Flat[]>(`${base(societyId)}/flats/`),
  });
}

export function useMembers(societyId: number) {
  return useQuery({
    queryKey: keys.members(societyId),
    queryFn: () => api<Member[]>(`${base(societyId)}/members/`),
  });
}

// --- Writes --------------------------------------------------------------------------------

/** Money changed: everything derived from the ledger is stale. */
function useInvalidateMoney(societyId: number) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: keys.summary(societyId) }),
      queryClient.invalidateQueries({ queryKey: keys.activity(societyId) }),
      queryClient.invalidateQueries({ queryKey: ["ledger", societyId] }),
      queryClient.invalidateQueries({ queryKey: keys.expenses(societyId) }),
      queryClient.invalidateQueries({ queryKey: keys.dues(societyId) }),
      queryClient.invalidateQueries({ queryKey: keys.audit(societyId) }),
    ]);
}

export function useRecordPayment(societyId: number) {
  const invalidate = useInvalidateMoney(societyId);
  return useMutation({
    mutationFn: (v: { flatId: number; amount: string; note: string; idempotencyKey: string }) =>
      api<LedgerEntry>(`${base(societyId)}/flats/${v.flatId}/payments/`, {
        method: "POST",
        body: { amount: v.amount, note: v.note },
        // The same key is reused if this exact submission is retried: no double payment.
        headers: { "Idempotency-Key": v.idempotencyKey },
      }),
    onSuccess: invalidate,
  });
}

export function useReverseEntry(societyId: number) {
  const invalidate = useInvalidateMoney(societyId);
  return useMutation({
    mutationFn: (v: { entryId: number; note: string }) =>
      api<LedgerEntry>(`${base(societyId)}/entries/${v.entryId}/reverse/`, {
        method: "POST",
        body: { note: v.note },
      }),
    onSuccess: invalidate,
  });
}

export function useRecordExpense(societyId: number) {
  const invalidate = useInvalidateMoney(societyId);
  return useMutation({
    mutationFn: (v: {
      category: ExpenseCategory;
      description: string;
      amount: string;
      paid_on: string;
      idempotencyKey: string;
    }) => {
      const { idempotencyKey, ...body } = v;
      return api(`${base(societyId)}/expenses/`, {
        method: "POST",
        body,
        headers: { "Idempotency-Key": idempotencyKey },
      });
    },
    onSuccess: invalidate,
  });
}

export function useReverseExpense(societyId: number) {
  const invalidate = useInvalidateMoney(societyId);
  return useMutation({
    mutationFn: (expenseId: number) =>
      api(`${base(societyId)}/expenses/${expenseId}/reverse/`, { method: "POST", body: {} }),
    onSuccess: invalidate,
  });
}

export function useSaveFlat(societyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: { id?: number; label: string; monthly_maintenance: string }) => {
      const { id, ...body } = v;
      return id === undefined
        ? api<Flat>(`${base(societyId)}/flats/`, { method: "POST", body })
        : api<Flat>(`${base(societyId)}/flats/${id}/`, { method: "PATCH", body });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.flats(societyId) }),
  });
}

export function useAddMember(societyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: { username: string; role: Role; flat: number | null }) =>
      api<Member>(`${base(societyId)}/members/`, { method: "POST", body: v }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.members(societyId) }),
  });
}

// --- Accounts and logins ----------------------------------------------------------------

export function useChangePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: { current_password: string; new_password: string }) =>
      api<Me>("/auth/change-password/", { method: "POST", body: v }),
    onSuccess: (me) => queryClient.setQueryData(keys.me, me),
  });
}

export function useCreateLogin(societyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: { name: string; role: Role; flat: number | null }) =>
      api<IssuedLogin>(`${base(societyId)}/people/`, { method: "POST", body: v }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.members(societyId) }),
  });
}

export function useReissueLogin(societyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (memberId: number) =>
      api<IssuedLogin>(`${base(societyId)}/members/${memberId}/reissue/`, {
        method: "POST",
        body: {},
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.members(societyId) }),
  });
}

export function useChangeMember(societyId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    // `flat` is only sent when it is meant to change; `null` clears it.
    mutationFn: (v: { memberId: number; role?: Role; flat?: number | null }) => {
      const { memberId, ...body } = v;
      return api<Member>(`${base(societyId)}/members/${memberId}/`, { method: "PATCH", body });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.members(societyId) });
      void queryClient.invalidateQueries({ queryKey: keys.audit(societyId) });
    },
  });
}

// --- Super admin (platform) ---------------------------------------------------------------

export function usePlatformSocieties() {
  return useQuery({
    queryKey: keys.platformSocieties,
    queryFn: () => api<PlatformSociety[]>("/platform/societies/"),
  });
}

export function useCreateSociety() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: { name: string; slug: string; president_name: string }) =>
      api<CreatedSociety>("/platform/societies/", { method: "POST", body: v }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.platformSocieties }),
  });
}

export function useReissueManager() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (v: { societyId: number; memberId: number }) =>
      api<IssuedLogin>(`/platform/societies/${v.societyId}/managers/${v.memberId}/reissue/`, {
        method: "POST",
        body: {},
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.platformSocieties }),
  });
}
