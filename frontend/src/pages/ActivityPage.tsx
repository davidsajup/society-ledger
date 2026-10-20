import { Badge, Card, Group, SegmentedControl, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import {
  IconArrowBackUp,
  IconCalendarDollar,
  IconCoin,
  IconReceipt2,
  IconShieldLock,
} from "@tabler/icons-react";
import { useMemo, useState } from "react";

import { useAudit, useBillingRuns, useFlats } from "../api/hooks";
import type { AuditRow } from "../api/types";
import { useMembership } from "../auth/session";
import { CardSkeleton, EmptyState, ErrorState, Money, formatDate } from "../components/common";
import { dayHeading, dayKey, monthLabel, timeLabel } from "../lib/dates";

type Filter = "all" | "payments" | "expenses" | "billing";

const GROUP: Record<AuditRow["action"], Exclude<Filter, "all">> = {
  "payment.recorded": "payments",
  "entry.reversed": "payments",
  "expense.recorded": "expenses",
  "expense.reversed": "expenses",
  "billing.run": "billing",
};

const LOOK: Record<AuditRow["action"], { icon: typeof IconCoin; color: string }> = {
  "payment.recorded": { icon: IconCoin, color: "teal" },
  "entry.reversed": { icon: IconArrowBackUp, color: "orange" },
  "billing.run": { icon: IconCalendarDollar, color: "violet" },
  "expense.recorded": { icon: IconReceipt2, color: "blue" },
  "expense.reversed": { icon: IconArrowBackUp, color: "orange" },
};

function describe(row: AuditRow, flatLabel: (id: number | null) => string): string {
  const who = row.actor === "system" ? "System" : row.actor;
  switch (row.action) {
    case "payment.recorded":
      return `${who} recorded a payment · Flat ${flatLabel(row.flat)}`;
    case "entry.reversed":
      return row.data.original_kind === "payment"
        ? `${who} reversed a payment · Flat ${flatLabel(row.flat)}`
        : `${who} cancelled a charge · Flat ${flatLabel(row.flat)}`;
    case "billing.run": {
      const flats = Number(row.data.flats_charged ?? 0);
      return `${who} billed ${flats} flat${flats === 1 ? "" : "s"} for ${monthLabel(`${row.data.period}-01`)}`;
    }
    case "expense.recorded":
      return `${who} recorded an expense · ${String(row.data.category ?? "other")}`;
    case "expense.reversed":
      return `${who} reversed an expense · ${String(row.data.category ?? "other")}`;
  }
}

export function ActivityPage() {
  const societyId = useMembership().society_id;
  const audit = useAudit(societyId);
  const runs = useBillingRuns(societyId);
  const flats = useFlats(societyId);
  const [filter, setFilter] = useState<Filter>("all");

  const labels = useMemo(() => new Map((flats.data ?? []).map((f) => [f.id, f.label])), [flats.data]);
  const flatLabel = (id: number | null) => (id === null ? "?" : (labels.get(id) ?? String(id)));

  const groups = useMemo(() => {
    const byDay = new Map<string, AuditRow[]>();
    for (const row of audit.data ?? []) {
      if (filter !== "all" && GROUP[row.action] !== filter) continue;
      const key = dayKey(row.created_at);
      byDay.set(key, [...(byDay.get(key) ?? []), row]);
    }
    return [...byDay.values()];
  }, [audit.data, filter]);

  return (
    <Stack gap="lg">
      <Stack gap="xs">
        <Title order={3}>Monthly billing</Title>
        {runs.isPending ? (
          <CardSkeleton rows={1} />
        ) : runs.isError ? (
          <ErrorState error={runs.error} onRetry={() => runs.refetch()} />
        ) : runs.data.length === 0 ? (
          <EmptyState title="No billing run yet">
            Dues are generated automatically for every flat on the 1st of each month.
          </EmptyState>
        ) : (
          runs.data.slice(0, 3).map((run) => (
            <Card key={run.id} padding="md">
              <Group justify="space-between" wrap="nowrap">
                <Group gap="sm" wrap="nowrap">
                  <ThemeIcon variant="light" color="violet" radius="xl" size="lg">
                    <IconCalendarDollar size={18} />
                  </ThemeIcon>
                  <div>
                    <Text fw={800}>{monthLabel(run.period)}</Text>
                    <Text size="xs" c="dimmed">
                      Generated {formatDate(run.created_at)} · {run.flats_charged} flats billed
                    </Text>
                  </div>
                </Group>
                <Money value={run.total_amount} fw={800} />
              </Group>
            </Card>
          ))
        )}
        <Text size="xs" c="dimmed">
          Each month is billed exactly once, even if the job runs twice.
        </Text>
      </Stack>

      <Stack gap="xs">
        <Group justify="space-between" align="flex-end">
          <Title order={3}>Who did what</Title>
        </Group>
        <Card padding="md" bg="var(--mantine-color-sunrise-light)" style={{ border: "none" }}>
          <Group gap="sm" wrap="nowrap" align="flex-start">
            <IconShieldLock size={20} color="var(--mantine-color-sunrise-7)" style={{ flexShrink: 0 }} />
            <Text size="sm">
              This log cannot be edited or deleted. Every money change is recorded here in the same
              step as the change itself, so nothing happens without a trace.
            </Text>
          </Group>
        </Card>

        <SegmentedControl
          fullWidth
          value={filter}
          onChange={(v) => setFilter(v as Filter)}
          data={[
            { value: "all", label: "All" },
            { value: "payments", label: "Payments" },
            { value: "expenses", label: "Expenses" },
            { value: "billing", label: "Billing" },
          ]}
        />

        {audit.isPending ? (
          <CardSkeleton rows={4} />
        ) : audit.isError ? (
          <ErrorState error={audit.error} onRetry={() => audit.refetch()} />
        ) : groups.length === 0 ? (
          <EmptyState title="Nothing here yet" />
        ) : (
          groups.map((rows) => (
            <Stack key={dayKey(rows[0].created_at)} gap={6}>
              <Text size="sm" fw={700} c="dimmed" mt="xs">
                {dayHeading(rows[0].created_at)}
              </Text>
              {rows.map((row) => {
                const look = LOOK[row.action];
                return (
                  <Card key={row.id} padding="sm">
                    <Group justify="space-between" wrap="nowrap" align="center">
                      <Group gap="sm" wrap="nowrap" miw={0}>
                        <ThemeIcon variant="light" color={look.color} radius="xl" size="lg">
                          <look.icon size={18} />
                        </ThemeIcon>
                        <div style={{ minWidth: 0 }}>
                          <Text fw={600} size="sm">
                            {describe(row, flatLabel)}
                          </Text>
                          <Group gap={6}>
                            <Text size="xs" c="dimmed">
                              {timeLabel(row.created_at)}
                            </Text>
                            {row.actor === "system" && (
                              <Badge size="xs" variant="light" color="gray">
                                automatic
                              </Badge>
                            )}
                          </Group>
                        </div>
                      </Group>
                      {row.amount && <Money value={row.amount} fw={700} />}
                    </Group>
                  </Card>
                );
              })}
            </Stack>
          ))
        )}
      </Stack>
    </Stack>
  );
}
