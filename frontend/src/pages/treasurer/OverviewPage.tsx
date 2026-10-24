import { Anchor, Badge, Button, Card, Group, Progress, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { IconCash, IconChevronDown, IconChevronRight, IconChevronUp } from "@tabler/icons-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useSummary } from "../../api/hooks";
import type { FlatBalance } from "../../api/types";
import { useMembership } from "../../auth/session";
import { can } from "../../lib/capabilities";
import { CardSkeleton, EmptyState, ErrorState, Money } from "../../components/common";
import { ClaimsWaitingNotice } from "../../components/ClaimsQueue";
import { RecordPaymentModal, type PayableFlat } from "../../components/RecordPaymentModal";
import { compareMoney, percent, toCents } from "../../lib/money";

export function OverviewPage() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const canRecord = can(membership.role, "recordPayment");
  const ownFlatId = membership.flat_id;
  const summary = useSummary(societyId);
  const [paying, setPaying] = useState<PayableFlat | null>(null);
  const [showPaid, setShowPaid] = useState(false);

  // Flats that owe come first, biggest debt on top; paid-up flats are a second, collapsed list.
  const { owing, paidUp } = useMemo(() => {
    const sorted = [...(summary.data?.flats ?? [])].sort(
      (a, b) => compareMoney(b.outstanding, a.outstanding) || a.label.localeCompare(b.label),
    );
    return {
      owing: sorted.filter((f) => toCents(f.outstanding) > 0n),
      paidUp: sorted.filter((f) => toCents(f.outstanding) <= 0n),
    };
  }, [summary.data]);

  if (summary.isPending) return <CardSkeleton rows={4} />;
  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;

  const { totals } = summary.data;
  const collectedPct = percent(totals.collected, totals.billed);
  const ownFlat = ownFlatId === null ? null : summary.data.flats.find((f) => f.id === ownFlatId);
  const allClear = owing.length === 0;
  // With nobody owing, the paid-up list is the whole page, so it starts open.
  const paidVisible = showPaid || allClear;

  function flatCard(flat: FlatBalance) {
    const owes = toCents(flat.outstanding) > 0n;
    return (
      <Card key={flat.id} padding="sm">
        <Group justify="space-between" wrap="nowrap" gap="sm">
          <Anchor
            component={Link}
            to={`/s/${societyId}/flat/${flat.id}/statement`}
            aria-label={`Flat ${flat.label}: open statement`}
            c="inherit"
            underline="never"
            mih={44}
            style={{ flex: 1, minWidth: 0, display: "flex", alignItems: "center", gap: 8 }}
          >
            <div style={{ minWidth: 0, flex: 1 }}>
              <Group gap="xs">
                <Text fw={800}>Flat {flat.label}</Text>
                {flat.id === ownFlatId && (
                  <Badge variant="outline">
                    Yours
                  </Badge>
                )}
                <Badge variant="light" color={owes ? "sunrise" : "teal"}>
                  {owes ? "Due" : "Paid up"}
                </Badge>
              </Group>
              <Text size="sm" c="dimmed">
                {owes ? (
                  <>
                    Owes <Money value={flat.outstanding} fw={700} c="var(--text-owing)" />
                    {toCents(flat.collected) > 0n && (
                      <>
                        {" "}
                        (<Money value={flat.collected} /> paid)
                      </>
                    )}
                  </>
                ) : (
                  <>
                    Paid <Money value={flat.collected} />
                  </>
                )}
              </Text>
            </div>
            <IconChevronRight size={20} aria-hidden style={{ flexShrink: 0, opacity: 0.6 }} />
          </Anchor>
          {canRecord && owes && flat.id !== ownFlatId && (
            <Button
              h={44}
              variant="light"
              leftSection={<IconCash size={18} />}
              aria-label={`Record payment for Flat ${flat.label}`}
              onClick={() => setPaying({ id: flat.id, label: flat.label, outstanding: flat.outstanding })}
            >
              Record
            </Button>
          )}
        </Group>
      </Card>
    );
  }

  return (
    <Stack gap="lg">
      <ClaimsWaitingNotice />
      <Card>
        <Title order={2} fz={{ base: 22, sm: 26 }} lh={1.25}>
          {allClear ? (
            "Every flat is paid up"
          ) : (
            <>
              {owing.length} {owing.length === 1 ? "flat still owes" : "flats still owe"}{" "}
              <Money value={totals.outstanding} inherit c="var(--text-owing)" />
            </>
          )}
        </Title>
        <Progress.Root
          size={22}
          radius="xl"
          mt="sm"
          style={{ border: "1px solid var(--mantine-color-default-border)" }}
          aria-label={`${collectedPct}% of the amount charged has been received`}
        >
          <Progress.Section value={collectedPct} color="var(--text-positive)" />
        </Progress.Root>
        <Text size="sm" mt="xs">
          <b>{collectedPct}% received:</b> <Money value={totals.collected} /> of{" "}
          <Money value={totals.billed} /> charged to date
        </Text>
        <Anchor
          component={Link}
          to={`/s/${societyId}/expenses`}
          size="sm"
          c="var(--text-owing)"
          mt="xs"
          mih={44}
          style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
        >
          Spent so far <Money value={totals.spent} fw={700} inherit /> · See expenses
          <IconChevronRight size={16} aria-hidden />
        </Anchor>
      </Card>

      {ownFlat && (
        <Card
          component={Link}
          to={`/s/${societyId}/home`}
          padding="sm"
          bg={
            toCents(ownFlat.outstanding) > 0n
              ? "var(--mantine-color-sunrise-light)"
              : "var(--mantine-color-teal-light)"
          }
          style={{ border: "none", textDecoration: "none", color: "inherit" }}
        >
          <Group justify="space-between" wrap="nowrap" mih={44}>
            <Text size="sm" fw={700}>
              Your flat {ownFlat.label}:{" "}
              {toCents(ownFlat.outstanding) > 0n ? (
                <>
                  you owe <Money value={ownFlat.outstanding} inherit />
                </>
              ) : (
                "you are paid up"
              )}
            </Text>
            <IconChevronRight size={20} aria-hidden />
          </Group>
          {toCents(ownFlat.outstanding) > 0n && (
            <Text size="sm">Another office-bearer records your payment.</Text>
          )}
        </Card>
      )}

      <Stack gap="xs">
        {summary.data.flats.length === 0 ? (
          <>
            <Title order={3}>Flats</Title>
            <EmptyState title="No flats yet">Add flats from the People page.</EmptyState>
          </>
        ) : (
          <>
            {!allClear && (
              <>
                <Title order={3}>Flats that owe ({owing.length})</Title>
                <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                  {owing.map(flatCard)}
                </SimpleGrid>
              </>
            )}

            {paidUp.length > 0 && (
              <>
                {allClear ? (
                  <Title order={3}>Paid-up flats ({paidUp.length})</Title>
                ) : (
                  <Button
                    variant="subtle"
                    color="gray"
                    h={44}
                    mt="xs"
                    justify="space-between"
                    fullWidth
                    aria-expanded={paidVisible}
                    rightSection={paidVisible ? <IconChevronUp size={18} /> : <IconChevronDown size={18} />}
                    onClick={() => setShowPaid((open) => !open)}
                  >
                    {paidVisible ? "Hide" : "Show"} {paidUp.length} paid-up {paidUp.length === 1 ? "flat" : "flats"}
                  </Button>
                )}
                {paidVisible && (
                  <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                    {paidUp.map(flatCard)}
                  </SimpleGrid>
                )}
              </>
            )}
          </>
        )}
      </Stack>

      <RecordPaymentModal societyId={societyId} flat={paying} onClose={() => setPaying(null)} />
    </Stack>
  );
}
