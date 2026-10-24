import { Button, Card, Group, Stack, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";

import { ApiError } from "../api/client";
import { useFlatClaims, useWithdrawClaim } from "../api/hooks";
import type { PaymentClaim } from "../api/types";
import { useMembership } from "../auth/session";
import { calendarDay } from "../lib/dates";
import { ClaimStatusBadge, METHOD_LABEL } from "./claims";
import { Money } from "./common";
import { ConfirmModal } from "./ConfirmModal";

const SHOWN = 5;

/** The payments this flat has reported, newest first, with what the treasurer decided. */
export function MyClaims() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const claims = useFlatClaims(societyId, membership.flat_id);
  const withdraw = useWithdrawClaim(societyId);
  const [target, setTarget] = useState<PaymentClaim | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Loading or failing quietly is right here: the page is useful without this list.
  const list = claims.data?.slice(0, SHOWN) ?? [];
  if (list.length === 0) return null;

  function confirmWithdraw() {
    if (!target) return;
    setError(null);
    withdraw.mutate(
      { claimId: target.id },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", title: "Withdrawn", message: "Nothing was changed" });
          setTarget(null);
        },
        onError: (e) => setError(e instanceof ApiError ? e.message : "Could not withdraw this."),
      },
    );
  }

  return (
    <Stack gap="xs">
      <Title order={3}>Payments you have reported</Title>
      {list.map((claim) => (
        <Card key={claim.id} padding="md">
          <Group justify="space-between" wrap="nowrap" align="flex-start" gap="sm">
            <div style={{ minWidth: 0 }}>
              <ClaimStatusBadge status={claim.status} />
              <Text fw={800} mt={6}>
                <Money value={claim.amount} inherit />
              </Text>
              <Text size="xs" c="dimmed">
                Paid {calendarDay(claim.paid_on)} · {METHOD_LABEL[claim.method]}
                {claim.reference ? ` · ${claim.reference}` : ""}
              </Text>
              {claim.status === "accepted" && claim.accepted_amount && claim.accepted_amount !== claim.amount && (
                <Text size="sm" mt={4}>
                  The treasurer recorded <Money value={claim.accepted_amount} fw={700} />.
                </Text>
              )}
              {claim.status === "rejected" && (
                <Text size="sm" mt={4}>
                  Reason: {claim.resolution_note}
                </Text>
              )}
            </div>
            {claim.status === "pending" && (
              <Button
                h={44}
                variant="subtle"
                color="gray"
                onClick={() => {
                  setError(null);
                  setTarget(claim);
                }}
              >
                Withdraw
              </Button>
            )}
          </Group>
        </Card>
      ))}

      <ConfirmModal
        opened={target !== null}
        title="Withdraw this report?"
        confirmLabel="Withdraw"
        loading={withdraw.isPending}
        error={error}
        onConfirm={confirmWithdraw}
        onClose={() => setTarget(null)}
      >
        The treasurer will no longer be asked to check it. Your balance does not change.
      </ConfirmModal>
    </Stack>
  );
}
