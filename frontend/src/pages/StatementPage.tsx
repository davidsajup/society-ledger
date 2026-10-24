import {
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Table,
  Text,
  ThemeIcon,
  Title,
} from "@mantine/core";
import { IconArrowLeft, IconPrinter, IconReceipt2 } from "@tabler/icons-react";
import { useMemo } from "react";
import { Link } from "react-router-dom";

import { useLedger } from "../api/hooks";
import { CardSkeleton, EmptyState, ErrorState, Money, formatDate } from "../components/common";
import { describeEntry, entryHeading, friendlyNote } from "../components/entries";
import { toCents } from "../lib/money";
import { buildStatement, receiptNumber } from "../lib/statement";
import { useStatementTarget } from "../lib/useStatementTarget";

/** A flat's passbook: every charge and payment, with what was owed after each one. */
export function StatementPage() {
  const target = useStatementTarget();
  const ledger = useLedger(target.societyId, target.flatId);
  const rows = useMemo(
    () => (ledger.data ? buildStatement(ledger.data.entries, ledger.data.outstanding) : []),
    [ledger.data],
  );

  if (target.flatId === null) {
    return <EmptyState title="No flat linked">Ask your society admin to link your flat.</EmptyState>;
  }
  if (ledger.isPending) return <CardSkeleton rows={5} />;
  if (ledger.isError) return <ErrorState error={ledger.error} onRetry={() => ledger.refetch()} />;

  const { flat, outstanding } = ledger.data;
  const owes = toCents(outstanding) > 0n;

  return (
    <Stack gap="lg">
      <Group justify="space-between" className="no-print">
        {target.staff ? (
          <Button component={Link} to={target.backPath} variant="subtle" color="gray" leftSection={<IconArrowLeft size={16} />}>
            All flats
          </Button>
        ) : (
          <span />
        )}
        <Button variant="light" h={44} leftSection={<IconPrinter size={16} />} onClick={() => window.print()}>
          Print
        </Button>
      </Group>

      <Card padding="lg">
        <Text size="sm" c="dimmed" fw={600}>
          {target.membership.society_name} · Statement
        </Text>
        <Title order={2}>Flat {flat.label}</Title>
        <Group justify="space-between" mt="sm" align="flex-end">
          <div>
            <Text size="sm" c="dimmed">
              {owes ? "Balance due" : "Account settled"}
            </Text>
            <Text className="money" fz={30} fw={800} c={owes ? "var(--text-owing)" : "var(--text-positive)"}>
              <Money value={outstanding} inherit />
            </Text>
          </div>
          <Text size="xs" c="dimmed">
            As of {formatDate(new Date().toISOString())}
          </Text>
        </Group>
      </Card>

      {rows.length === 0 ? (
        <EmptyState title="No entries yet">Charges and payments will appear here.</EmptyState>
      ) : (
        <>
          {/* Wide screens: a proper passbook table. */}
          <Card padding={0} visibleFrom="sm">
            <Table verticalSpacing="sm" horizontalSpacing="md" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Date</Table.Th>
                  <Table.Th>Details</Table.Th>
                  <Table.Th ta="right">Charged</Table.Th>
                  <Table.Th ta="right">Paid</Table.Th>
                  <Table.Th ta="right">Balance</Table.Th>
                  <Table.Th className="no-print" />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {rows.map(({ entry, balanceAfter, reversed, isReceiptable }) => {
                  const look = describeEntry(entry);
                  const charge = entry.kind === "charge";
                  return (
                    <Table.Tr key={entry.id} style={{ opacity: reversed ? 0.6 : 1 }}>
                      <Table.Td className="money">{formatDate(entry.created_at)}</Table.Td>
                      <Table.Td>
                        <Group gap={6}>
                          <Text fw={600} size="sm">
                            {entryHeading(entry, look)}
                          </Text>
                          {reversed && (
                            <Badge color="orange" variant="light">
                              Reversed
                            </Badge>
                          )}
                        </Group>
                        <Text size="xs" c="dimmed">
                          {entry.note ? friendlyNote(entry.note) : "—"} · by {entry.recorded_by}
                        </Text>
                      </Table.Td>
                      <Table.Td ta="right" className="money">
                        {charge ? <Money value={entry.amount} /> : ""}
                      </Table.Td>
                      <Table.Td ta="right" className="money">
                        {charge ? "" : <Money value={entry.amount} c="var(--text-positive)" />}
                      </Table.Td>
                      <Table.Td ta="right" fw={700}>
                        <Money value={balanceAfter} />
                      </Table.Td>
                      <Table.Td ta="right" className="no-print">
                        {isReceiptable && (
                          <Button component={Link} to={target.receiptPath(entry.id)} h={44} variant="subtle" leftSection={<IconReceipt2 size={14} />}>
                            Receipt
                          </Button>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Card>

          {/* Phones: the same rows as cards, each with its balance underneath. */}
          <Stack gap="xs" hiddenFrom="sm">
            {rows.map(({ entry, balanceAfter, reversed, isReceiptable }) => {
              const look = describeEntry(entry);
              return (
                <Card key={entry.id} padding="md" style={{ opacity: reversed ? 0.65 : 1 }}>
                  <Group justify="space-between" wrap="nowrap" align="flex-start">
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
                    <Text fw={800} className="money" c={look.sign === "−" ? "var(--text-positive)" : undefined}>
                      <Money value={entry.amount} />
                    </Text>
                  </Group>
                  <Group justify="space-between" mt="xs">
                    <Group gap={6}>
                      <Text size="xs" c="dimmed">
                        Balance after: <Money value={balanceAfter} fw={700} />
                      </Text>
                      {reversed && (
                        <Badge color="orange" variant="light">
                          Reversed
                        </Badge>
                      )}
                    </Group>
                    {isReceiptable && (
                      <Button component={Link} to={target.receiptPath(entry.id)} h={44} variant="light" leftSection={<IconReceipt2 size={14} />} className="no-print">
                        {receiptNumber(entry.id)}
                      </Button>
                    )}
                  </Group>
                </Card>
              );
            })}
          </Stack>
        </>
      )}
    </Stack>
  );
}
