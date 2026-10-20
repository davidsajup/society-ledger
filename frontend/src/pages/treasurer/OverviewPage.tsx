import { Badge, Button, Card, Group, Progress, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { IconCash } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useSummary } from "../../api/hooks";
import { useMembership } from "../../auth/session";
import { can } from "../../lib/capabilities";
import { CardSkeleton, EmptyState, ErrorState, Money, StatCard } from "../../components/common";
import { RecordPaymentModal, type PayableFlat } from "../../components/RecordPaymentModal";
import { compareMoney, percent, toCents } from "../../lib/money";

export function OverviewPage() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const canRecord = can(membership.role, "recordPayment");
  const ownFlatId = membership.flat_id;
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

  const ownFlat = ownFlatId === null ? null : summary.data.flats.find((f) => f.id === ownFlatId);

  return (
    <Stack gap="lg">
      {ownFlat && (
        <Card
          component={Link}
          to={`/s/${societyId}/home`}
          bg={
            toCents(ownFlat.outstanding) > 0n
              ? "var(--mantine-color-sunrise-light)"
              : "var(--mantine-color-teal-light)"
          }
          style={{ border: "none", textDecoration: "none", color: "inherit" }}
        >
          <Group justify="space-between" wrap="nowrap">
            <div>
              <Text size="sm" fw={700}>
                Your dues · Flat {ownFlat.label}
              </Text>
              <Text size="sm" c="dimmed">
                {toCents(ownFlat.outstanding) > 0n
                  ? "Another office-bearer records your payment."
                  : "You're all paid up."}
              </Text>
            </div>
            <Text className="money" fz={26} fw={800}>
              <Money value={ownFlat.outstanding} inherit />
            </Text>
          </Group>
        </Card>
      )}

      <SimpleGrid cols={{ base: 2, sm: 4 }} spacing="sm">
        <StatCard label="Billed" value={totals.billed} />
        <StatCard label="Collected" value={totals.collected} color="teal.7" />
        <StatCard
          label="Outstanding"
          value={totals.outstanding}
          color={toCents(totals.outstanding) > 0n ? "sunrise.7" : undefined}
        />
        <Link
          to={`/s/${societyId}/expenses`}
          style={{ textDecoration: "none", color: "inherit" }}
          aria-label="Spent: view expenses"
        >
          <StatCard label="Spent" value={totals.spent} hint="View expenses →" />
        </Link>
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
                        {flat.id === ownFlatId && (
                          <Badge variant="outline" size="sm">
                            Yours
                          </Badge>
                        )}
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
                    <Stack gap={2} align="flex-end">
                      {canRecord && owes && flat.id !== ownFlatId && (
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
                      <Button
                        component={Link}
                        to={`/s/${societyId}/flat/${flat.id}/statement`}
                        size="compact-xs"
                        variant="subtle"
                        color="gray"
                      >
                        Statement
                      </Button>
                    </Stack>
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
