import { Badge, Button, Card, Divider, Group, Stack, Text, Title } from "@mantine/core";
import { IconArrowLeft, IconPrinter } from "@tabler/icons-react";
import { useMemo } from "react";
import { Link, useParams } from "react-router-dom";

import { useLedger } from "../api/hooks";
import { CardSkeleton, EmptyState, ErrorState, Money, formatDate } from "../components/common";
import { buildStatement, receiptNumber } from "../lib/statement";
import { useStatementTarget } from "../lib/useStatementTarget";

/** A printable payment receipt. A reversed payment is stamped VOID so it cannot be reused. */
export function ReceiptPage() {
  const target = useStatementTarget();
  const { entryId } = useParams();
  const ledger = useLedger(target.societyId, target.flatId);
  const rows = useMemo(
    () => (ledger.data ? buildStatement(ledger.data.entries, ledger.data.outstanding) : []),
    [ledger.data],
  );

  if (ledger.isPending) return <CardSkeleton rows={3} />;
  if (ledger.isError) return <ErrorState error={ledger.error} onRetry={() => ledger.refetch()} />;

  const row = rows.find((r) => String(r.entry.id) === entryId && r.isReceiptable);
  if (!row) {
    return (
      <Stack>
        <EmptyState title="Receipt not found">
          Only recorded payments have receipts, and very old entries may not be listed.
        </EmptyState>
        <Button component={Link} to={target.statementPath} variant="subtle" leftSection={<IconArrowLeft size={16} />}>
          Back to statement
        </Button>
      </Stack>
    );
  }

  const { entry, balanceAfter, reversed } = row;
  const line = (label: string, value: React.ReactNode) => (
    <Group justify="space-between" wrap="nowrap" align="flex-start">
      <Text c="dimmed" size="sm">
        {label}
      </Text>
      <Text fw={600} ta="right">
        {value}
      </Text>
    </Group>
  );

  return (
    <Stack gap="md" maw={520} mx="auto">
      <Group justify="space-between" className="no-print">
        <Button component={Link} to={target.statementPath} variant="subtle" color="gray" leftSection={<IconArrowLeft size={16} />}>
          Statement
        </Button>
        <Button leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>
          Print / save as PDF
        </Button>
      </Group>

      <Card padding="xl" className="receipt">
        <Stack gap="md">
          {reversed && (
            <Badge
              color="red"
              variant="outline"
              size="xl"
              w="fit-content"
              style={{ borderWidth: 3, letterSpacing: 1 }}
            >
              VOID · reversed
            </Badge>
          )}

          <div>
            <Text size="sm" c="dimmed" fw={700} tt="uppercase">
              Payment receipt
            </Text>
            <Title order={2}>{target.membership.society_name}</Title>
          </div>

          <Divider />

          <div>
            <Text size="sm" c="dimmed">
              Amount received
            </Text>
            <Text className="money" fz={38} fw={800} td={reversed ? "line-through" : undefined}>
              <Money value={entry.amount} inherit />
            </Text>
          </div>

          <Stack gap={8}>
            {line("Receipt no.", receiptNumber(entry.id))}
            {line("Date", formatDate(entry.created_at))}
            {line("Flat", ledger.data.flat.label)}
            {line("Received by", entry.recorded_by)}
            {entry.note && line("Note", entry.note)}
            {line("Balance after this payment", <Money value={balanceAfter} />)}
          </Stack>

          <Divider />
          <Text size="xs" c="dimmed">
            Generated from the society ledger. Entries in the ledger are never edited or deleted; if
            a payment is cancelled, it is reversed and this receipt is marked void.
          </Text>
        </Stack>
      </Card>
    </Stack>
  );
}
