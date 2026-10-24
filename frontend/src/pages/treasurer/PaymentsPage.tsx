import { Badge, Button, Card, Group, Stack, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowBackUp } from "@tabler/icons-react";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { useActivity, useReverseEntry } from "../../api/hooks";
import type { RecentPayment } from "../../api/types";
import { useMembership } from "../../auth/session";
import { CardSkeleton, EmptyState, ErrorState, Money, formatDate } from "../../components/common";
import { ConfirmModal } from "../../components/ConfirmModal";
import { friendlyNote } from "../../components/entries";

export function PaymentsPage() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const activity = useActivity(societyId);
  const reverse = useReverseEntry(societyId);
  const [target, setTarget] = useState<RecentPayment | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (activity.isPending) return <CardSkeleton rows={5} />;
  if (activity.isError) return <ErrorState error={activity.error} onRetry={() => activity.refetch()} />;

  function confirm() {
    if (!target) return;
    setError(null);
    reverse.mutate(
      { entryId: target.id, note: "Reversed by treasurer" },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", title: "Payment reversed", message: `Flat ${target.flat_label}` });
          setTarget(null);
        },
        onError: (e) => setError(e instanceof ApiError ? e.message : "Could not reverse the payment."),
      },
    );
  }

  return (
    <Stack gap="xs">
      <Title order={3}>Recent payments</Title>
      <Text size="sm" c="dimmed">
        Payments are never edited or deleted. A mistake is corrected by reversing the payment, which
        keeps the record honest.
      </Text>
      {activity.data.length === 0 ? (
        <EmptyState title="No payments yet">Record a payment from the Overview page.</EmptyState>
      ) : (
        activity.data.map((payment) => (
          <Card key={payment.id} padding="md">
            <Group justify="space-between" wrap="nowrap" align="flex-start">
              <div style={{ minWidth: 0 }}>
                <Group gap="xs">
                  <Text fw={800}>Flat {payment.flat_label}</Text>
                  {payment.is_reversal && (
                    <Badge variant="light" color="gray">
                      Charge cancelled
                    </Badge>
                  )}
                  {payment.reversed && (
                    <Badge variant="light" color="orange">
                      Reversed
                    </Badge>
                  )}
                </Group>
                <Text size="xs" c="dimmed">
                  {formatDate(payment.created_at)} · by {payment.recorded_by}
                  {payment.note ? ` · ${friendlyNote(payment.note)}` : ""}
                </Text>
              </div>
              <Stack gap={4} align="flex-end">
                <Money
                  value={payment.amount}
                  fw={800}
                  td={payment.reversed ? "line-through" : undefined}
                  c={payment.reversed ? "dimmed" : "var(--text-positive)"}
                />
                {!payment.reversed && !payment.is_reversal && payment.flat_id === membership.flat_id && (
                  <Text size="xs" c="dimmed">
                    Your flat: another office-bearer reverses this
                  </Text>
                )}
                {!payment.reversed && !payment.is_reversal && payment.flat_id !== membership.flat_id && (
                  <Button
                    h={44}
                    variant="subtle"
                    color="red"
                    leftSection={<IconArrowBackUp size={14} />}
                    onClick={() => {
                      setError(null);
                      setTarget(payment);
                    }}
                  >
                    Reverse
                  </Button>
                )}
              </Stack>
            </Group>
          </Card>
        ))
      )}

      <ConfirmModal
        opened={target !== null}
        title="Reverse this payment?"
        confirmLabel="Reverse payment"
        loading={reverse.isPending}
        error={error}
        onConfirm={confirm}
        onClose={() => setTarget(null)}
      >
        {target && (
          <>
            This puts <Money value={target.amount} fw={700} /> back on Flat {target.flat_label}&apos;s
            dues. The original payment stays in the history, marked as reversed.
          </>
        )}
      </ConfirmModal>
    </Stack>
  );
}
