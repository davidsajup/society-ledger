import { Badge, Card, Group, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import {
  IconArrowBackUp,
  IconCircleCheck,
  IconCoin,
  IconReceipt,
} from "@tabler/icons-react";

import { useLedger } from "../api/hooks";
import type { LedgerEntry } from "../api/types";
import { useMembership } from "../auth/session";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  Money,
  formatDate,
} from "../components/common";
import { toCents } from "../lib/money";

function describe(entry: LedgerEntry) {
  if (entry.reverses !== null) {
    return entry.kind === "charge"
      ? { title: "Payment reversed", icon: IconArrowBackUp, color: "orange", sign: "+" }
      : { title: "Charge cancelled", icon: IconArrowBackUp, color: "teal", sign: "−" };
  }
  return entry.kind === "charge"
    ? { title: "Maintenance due", icon: IconReceipt, color: "gray", sign: "+" }
    : { title: "Payment received", icon: IconCoin, color: "teal", sign: "−" };
}

export function ResidentDashboard() {
  const membership = useMembership();
  const ledger = useLedger(membership.society_id, membership.flat_id);

  if (membership.flat_id === null) {
    return <EmptyState title="No flat linked">Ask your society admin to link your flat.</EmptyState>;
  }
  if (ledger.isPending) return <CardSkeleton rows={4} />;
  if (ledger.isError) return <ErrorState error={ledger.error} onRetry={() => ledger.refetch()} />;

  const { flat, outstanding, entries } = ledger.data;
  const owes = toCents(outstanding) > 0n;

  return (
    <Stack gap="lg">
      <Card
        padding="xl"
        bg={owes ? "var(--mantine-color-sunrise-light)" : "var(--mantine-color-teal-light)"}
        style={{ border: "none" }}
      >
        <Group gap="xs" mb="xs">
          <ThemeIcon variant="white" color={owes ? "sunrise" : "teal"} radius="xl" size="lg">
            {owes ? <IconReceipt size={20} /> : <IconCircleCheck size={20} />}
          </ThemeIcon>
          <Text fw={700}>Flat {flat.label}</Text>
        </Group>
        <Text size="sm" c="dimmed" fw={600}>
          {owes ? "You currently owe" : "You're all paid up"}
        </Text>
        <div className="balance">
          <Money value={outstanding} inherit />
        </div>
        <Text size="sm" c="dimmed" mt={6}>
          {owes
            ? "Pay your society treasurer, who will record it here."
            : "Nothing is due. Thank you!"}
        </Text>
      </Card>

      <Stack gap="xs">
        <Title order={3}>Your history</Title>
        {entries.length === 0 ? (
          <EmptyState title="Nothing yet">Charges and payments will appear here.</EmptyState>
        ) : (
          entries.map((entry) => {
            const d = describe(entry);
            return (
              <Card key={entry.id} padding="md">
                <Group justify="space-between" wrap="nowrap" align="center">
                  <Group gap="sm" wrap="nowrap" miw={0}>
                    <ThemeIcon variant="light" color={d.color} radius="xl" size="lg">
                      <d.icon size={18} />
                    </ThemeIcon>
                    <div style={{ minWidth: 0 }}>
                      <Text fw={700} truncate>
                        {d.title}
                      </Text>
                      <Text size="xs" c="dimmed" truncate>
                        {formatDate(entry.created_at)}
                        {entry.note ? ` · ${entry.note}` : ""}
                      </Text>
                    </div>
                  </Group>
                  <Group gap={6} wrap="nowrap">
                    <Text fw={800} c={d.sign === "−" ? "teal.7" : undefined} className="money">
                      {d.sign}
                      <Money value={entry.amount} />
                    </Text>
                  </Group>
                </Group>
                {entry.reverses !== null && (
                  <Badge variant="light" color="gray" mt="xs" size="sm" w="fit-content">
                    Correction
                  </Badge>
                )}
              </Card>
            );
          })
        )}
      </Stack>
    </Stack>
  );
}
