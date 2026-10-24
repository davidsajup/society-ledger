import { Button, Card, Group, Stack, Text, ThemeIcon, Title } from "@mantine/core";
import { IconCircleCheck, IconReceipt } from "@tabler/icons-react";
import { Link } from "react-router-dom";

import { useLedger } from "../api/hooks";
import { useMembership } from "../auth/session";
import {
  CardSkeleton,
  EmptyState,
  ErrorState,
  Money,
  formatDate,
} from "../components/common";
import { describeEntry, entryHeading, friendlyNote } from "../components/entries";
import { toCents } from "../lib/money";

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
  const recent = entries.slice(0, 5);

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
        <Text size="sm" fw={600}>
          {owes ? "You currently owe" : "You're all paid up"}
        </Text>
        <div className="balance">
          <Money value={outstanding} inherit />
        </div>
        <Text size="sm" mt={6}>
          {owes
            ? membership.role === "resident"
              ? "Pay your society treasurer, who will record it here."
              : "Ask another office-bearer to record your payment."
            : "Nothing is due. Thank you!"}
        </Text>
      </Card>

      <Stack gap="xs">
        <Group justify="space-between" align="center">
          <Title order={3}>Recent activity</Title>
          <Button component={Link} to={`/s/${membership.society_id}/statement`} variant="light" h={44}>
            All payments &amp; receipts
          </Button>
        </Group>
        {recent.length === 0 ? (
          <EmptyState title="Nothing yet">Charges and payments will appear here.</EmptyState>
        ) : (
          recent.map((entry) => {
            const look = describeEntry(entry);
            return (
              <Card key={entry.id} padding="md">
                <Group justify="space-between" wrap="nowrap" align="center">
                  <Group gap="sm" wrap="nowrap" miw={0}>
                    <ThemeIcon variant="light" color={look.color} radius="xl" size="lg">
                      <look.icon size={18} />
                    </ThemeIcon>
                    <div style={{ minWidth: 0 }}>
                      <Text fw={700}>{entryHeading(entry, look)}</Text>
                      <Text size="xs" c="dimmed">
                        {formatDate(entry.created_at)}
                        {entry.note ? ` · ${friendlyNote(entry.note)}` : ""}
                      </Text>
                    </div>
                  </Group>
                  <Text fw={800} c={look.sign === "−" ? "var(--text-positive)" : undefined} className="money">
                    <Money value={entry.amount} />
                  </Text>
                </Group>
              </Card>
            );
          })
        )}
      </Stack>
    </Stack>
  );
}
