import {
  Box,
  Button,
  Card,
  Group,
  ScrollArea,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { IconCheck, IconMail } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useDues } from "../api/hooks";
import type { DuesCell, DuesFlat, DuesStatus } from "../api/types";
import { useMembership } from "../auth/session";
import { CardSkeleton, EmptyState, ErrorState, Money } from "../components/common";
import { RemindersModal } from "../components/RemindersModal";
import { can } from "../lib/capabilities";
import { cycleLabel, cycleShortLabel, cycleWord } from "../lib/dates";
import { compareMoney, formatInr, toCents } from "../lib/money";

const STYLE: Record<DuesStatus, { bg: string; fg: string; word: string }> = {
  paid: { bg: "var(--mantine-color-teal-light)", fg: "var(--mantine-color-teal-light-color)", word: "Paid" },
  partial: { bg: "var(--mantine-color-yellow-light)", fg: "var(--mantine-color-yellow-light-color)", word: "Part-paid" },
  unpaid: { bg: "var(--mantine-color-red-light)", fg: "var(--mantine-color-red-light-color)", word: "Unpaid" },
  none: { bg: "transparent", fg: "var(--mantine-color-dimmed)", word: "Not billed" },
};

/** One billing cycle for one flat: colour AND a word/figure, so it never relies on colour alone. */
function Chip({ cell, cycle }: { cell: DuesCell; cycle: number }) {
  const s = STYLE[cell.status];
  return (
    <Box
      title={`${cycleLabel(cell.period, cycle)} · ${s.word}${cell.status === "none" ? "" : ` · due ${formatInr(cell.due)}`}`}
      style={{ background: s.bg, color: s.fg, borderRadius: "var(--mantine-radius-md)", minWidth: 62 }}
      px={8}
      py={5}
      ta="center"
    >
      <Text size="xs" fw={700} inherit>
        {cycleShortLabel(cell.period, cycle)}
      </Text>
      <Text size="xs" inherit className="money">
        {cell.status === "paid" ? <IconCheck size={13} style={{ verticalAlign: "-2px" }} /> : cell.status === "none" ? "—" : formatInr(cell.due, true)}
      </Text>
    </Box>
  );
}

export function DuesPage() {
  const societyId = useMembership().society_id;
  const dues = useDues(societyId);
  const [only, setOnly] = useState<"all" | "due">("due");
  const [reminding, setReminding] = useState(false);
  const role = useMembership().role;

  const flats = useMemo(() => {
    const all = [...(dues.data?.flats ?? [])].sort(
      (a, b) => compareMoney(b.outstanding, a.outstanding) || a.label.localeCompare(b.label),
    );
    return only === "due" ? all.filter((f) => toCents(f.outstanding) > 0n) : all;
  }, [dues.data, only]);

  if (dues.isPending) return <CardSkeleton rows={5} />;
  if (dues.isError) return <ErrorState error={dues.error} onRetry={() => dues.refetch()} />;

  const { periods, summary, cycle_months: cycle } = dues.data;
  const statement = (flat: DuesFlat) => `/s/${societyId}/flat/${flat.id}/statement`;

  return (
    <Stack gap="lg">
      <Card>
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <div>
            <Title order={3}>Dues by {cycleWord(cycle)}</Title>
            <Text c="dimmed" size="sm">
              {summary.flats_with_dues === 0
                ? `All ${summary.flats} flats are paid up.`
                : `${summary.flats_with_dues} of ${summary.flats} flats have dues` +
                  (summary.oldest_unpaid ? ` · oldest unpaid: ${cycleLabel(summary.oldest_unpaid, cycle)}` : "")}
            </Text>
          </div>
          <SegmentedControl
            value={only}
            onChange={(v) => setOnly(v as "all" | "due")}
            data={[
              { value: "due", label: "With dues" },
              { value: "all", label: "All flats" },
            ]}
          />
        </Group>
        {can(role, "sendReminders") && summary.flats_with_dues > 0 && (
          <Button
            variant="light"
            h={44}
            mt="sm"
            leftSection={<IconMail size={18} />}
            onClick={() => setReminding(true)}
          >
            Remind flats that owe
          </Button>
        )}
        <Text size="xs" c="dimmed" mt="sm">
          Payments are applied to the oldest dues first. This view is calculated from the ledger,
          so it always agrees with each flat&apos;s balance.
        </Text>
        <Button component={Link} to={`/s/${societyId}/billing`} variant="subtle" h={44} px={0} mt={4}>
          How billing works and the billing schedule
        </Button>
      </Card>

      {periods.length === 0 ? (
        <EmptyState title="Nothing billed yet">
          Dues appear here after the first billing run.
        </EmptyState>
      ) : flats.length === 0 ? (
        <EmptyState title="No flats with dues">Everyone is paid up. Switch to All flats to see the grid.</EmptyState>
      ) : (
        <>
          {/* Wide screens: flats down the side, billing cycles across. */}
          <Card padding={0} visibleFrom="md">
            <ScrollArea>
              <Table verticalSpacing="xs" horizontalSpacing="md" highlightOnHover>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Flat</Table.Th>
                    {periods.map((p) => (
                      <Table.Th key={p} ta="center">
                        {cycleShortLabel(p, cycle)} {p.slice(2, 4)}
                      </Table.Th>
                    ))}
                    <Table.Th ta="right">Owes</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {flats.map((flat) => (
                    <Table.Tr key={flat.id}>
                      <Table.Td>
                        <Button component={Link} to={statement(flat)} variant="subtle" h={44}>
                          {flat.label}
                        </Button>
                      </Table.Td>
                      {flat.cells.map((cell) => (
                        <Table.Td key={cell.period}>
                          <Chip cell={cell} cycle={cycle} />
                        </Table.Td>
                      ))}
                      <Table.Td ta="right" fw={800}>
                        <Money value={flat.outstanding} c={toCents(flat.outstanding) > 0n ? "var(--text-owing)" : "var(--text-positive)"} />
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </Card>

          {/* Phones and tablets: one card per flat with its billing cycles as chips. */}
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" hiddenFrom="md">
            {flats.map((flat) => (
              <Card key={flat.id} padding="md">
                <Group justify="space-between" wrap="nowrap" mb="sm">
                  <Button component={Link} to={statement(flat)} variant="subtle" h={44} px={0}>
                    <Text fw={800} inherit>
                      Flat {flat.label}
                    </Text>
                  </Button>
                  <Text fw={800} className="money" c={toCents(flat.outstanding) > 0n ? "var(--text-owing)" : "var(--text-positive)"}>
                    {toCents(flat.outstanding) > 0n ? (
                      <>
                        owes <Money value={flat.outstanding} inherit />
                      </>
                    ) : (
                      "paid up"
                    )}
                  </Text>
                </Group>
                <Group gap={6}>
                  {flat.cells.map((cell) => (
                    <Chip key={cell.period} cell={cell} cycle={cycle} />
                  ))}
                </Group>
              </Card>
            ))}
          </SimpleGrid>
        </>
      )}

      <RemindersModal opened={reminding} societyId={societyId} onClose={() => setReminding(false)} />
    </Stack>
  );
}
