import { Badge, Button, Card, Group, Progress, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { IconCash } from "@tabler/icons-react";
import { useMemo, useState } from "react";

import { useSummary } from "../../api/hooks";
import { useMembership } from "../../auth/session";
import { CardSkeleton, EmptyState, ErrorState, Money, StatCard } from "../../components/common";
import { RecordPaymentModal, type PayableFlat } from "../../components/RecordPaymentModal";
import { compareMoney, percent, toCents } from "../../lib/money";

export function OverviewPage() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const canRecord = membership.role === "treasurer";
  const summary = useSummary(societyId);
  const [paying, setPaying] = useState<PayableFlat | null>(null);

  const flats = useMemo(
    () =>
      [...(summary.data?.flats ?? [])].sort(
        (a, b) => compareMoney(b.outstanding, a.outstanding) || a.label.localeCompare(b.label),
      ),
    [summary.data],
  );

  if (summary.isPending) return <CardSkeleton rows={4} />;
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;

  const { totals } = summary.data;
  const collectedPct = percent(totals.collected, totals.billed);

  return (
    <Stack gap="lg">
      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
        <StatCard label="Billed" value={totals.billed} />
        <StatCard label="Collected" value={totals.collected} color="teal.7" />
        <StatCard
          label="Outstanding"
          value={totals.outstanding}
          color={toCents(totals.outstanding) > 0n ? "sunrise.7" : undefined}
        />
        <StatCard label="Spent" value={totals.spent} />
      </SimpleGrid>

      <Card>
        <Group justify="space-between" mb="xs">
          <Text fw={700}>Collections vs outstanding</Text>
          <Text fw={800} c="teal.7">
            {collectedPct}% collected
          </Text>
        </Group>
        <Progress.Root size={22} radius="xl" aria-label={`${collectedPct}% of billed amount collected`}>
          <Progress.Section value={collectedPct} color="teal" />
          <Progress.Section value={100 - collectedPct} color="sunrise.2" />
        </Progress.Root>
        <Group justify="space-between" mt="xs">
          <Text size="xs" c="dimmed">
            Collected <Money value={totals.collected} />
          </Text>
          <Text size="xs" c="dimmed">
            Still due <Money value={totals.outstanding} />
          </Text>
        </Group>
      </Card>

      <Stack gap="xs">
        <Title order={3}>Flats</Title>
        {flats.length === 0 ? (
          <EmptyState title="No flats yet">Add flats from the Flats page.</EmptyState>
        ) : (
          <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
            {flats.map((flat) => {
              const owes = toCents(flat.outstanding) > 0n;
              return (
                <Card key={flat.id} padding="md">
                  <Group justify="space-between" wrap="nowrap">
                    <div>
                      <Group gap="xs">
                        <Text fw={800}>Flat {flat.label}</Text>
                        <Badge variant="light" color={owes ? "sunrise" : "teal"} size="sm">
                          {owes ? "Due" : "Paid up"}
                        </Badge>
                      </Group>
                      <Text size="sm" c="dimmed">
                        {owes ? (
                          <>
                            Owes <Money value={flat.outstanding} fw={700} c="sunrise.8" /> of{" "}
                            <Money value={flat.billed} />
                          </>
                        ) : (
                          <>
                            Paid <Money value={flat.collected} />
                          </>
                        )}
                      </Text>
                    </div>
                    {canRecord && owes && (
                      <Button
                        size="compact-md"
                        variant="light"
                        leftSection={<IconCash size={16} />}
                        onClick={() =>
                          setPaying({ id: flat.id, label: flat.label, outstanding: flat.outstanding })
                        }
                      >
                        Record
                      </Button>
                    )}
                  </Group>
                  <Progress
                    mt="sm"
                    size="sm"
                    radius="xl"
                    color="teal"
                    value={percent(flat.collected, flat.billed)}
                    aria-label="Share of billed amount paid"
                  />
                </Card>
              );
            })}
          </SimpleGrid>
        )}
      </Stack>

      <RecordPaymentModal societyId={societyId} flat={paying} onClose={() => setPaying(null)} />
    </Stack>
  );
}
