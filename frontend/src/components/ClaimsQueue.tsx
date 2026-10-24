import { Alert, Anchor, Button, Card, Group, Modal, Stack, Text, Textarea, TextInput, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconInbox } from "@tabler/icons-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../api/client";
import { useAcceptClaim, useClaimQueue, useRejectClaim } from "../api/hooks";
import type { PaymentClaim } from "../api/types";
import { useMembership } from "../auth/session";
import { calendarDay } from "../lib/dates";
import { isValidAmount, normaliseAmount } from "../lib/money";
import { METHOD_LABEL } from "./claims";
import { CardSkeleton, ErrorState, Money, formatDate } from "./common";

/** The 409 the server sends when the same amount was recorded for this flat moments ago. */
function earlierPaymentFrom(error: unknown): { amount: string; createdAt: string } | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const data = error.data as { code?: string; previous?: { amount: string; created_at: string } };
  if (data?.code !== "possible_duplicate" || !data.previous) return null;
  return { amount: data.previous.amount, createdAt: data.previous.created_at };
}

function AcceptModal({
  claim,
  societyId,
  onClose,
}: {
  claim: PaymentClaim | null;
  societyId: number;
  onClose: () => void;
}) {
  const accept = useAcceptClaim(societyId);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [earlier, setEarlier] = useState<{ amount: string; createdAt: string } | null>(null);

  useEffect(() => {
    if (claim) {
      setAmount(claim.amount);
      setError(null);
      setEarlier(null);
      accept.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when a different claim opens
  }, [claim?.id]);

  if (!claim) return <Modal opened={false} onClose={onClose} />;

  const trimmed = amount.trim();
  const valid = isValidAmount(trimmed);

  function send(confirmDuplicate: boolean) {
    if (!claim || !valid) return;
    setError(null);
    setEarlier(null);
    accept.mutate(
      { claimId: claim.id, amount: normaliseAmount(trimmed), confirmDuplicate },
      {
        onSuccess: () => {
          notifications.show({
            color: "teal",
            title: "Payment recorded",
            message: `Flat ${claim.flat_label}`,
          });
          onClose();
        },
        onError: (e) => {
          const duplicate = earlierPaymentFrom(e);
          if (duplicate) return setEarlier(duplicate);
          setError(
            e instanceof ApiError
              ? (e.fieldError("amount") ?? e.message)
              : "Could not record the payment.",
          );
        },
      },
    );
  }

  return (
    <Modal opened onClose={onClose} title={`Record this payment · Flat ${claim.flat_label}`} centered>
      <Stack>
        <Text size="sm">
          {claim.claimed_by_name} says <Money value={claim.amount} fw={700} /> was paid on{" "}
          {calendarDay(claim.paid_on)} by {METHOD_LABEL[claim.method]}
          {claim.reference ? `, reference ${claim.reference}` : ""}. Check your bank or cash book
          first.
        </Text>
        <TextInput
          label="Amount you received (₹)"
          description="Change it if the bank shows a different figure. The report keeps both numbers."
          inputMode="decimal"
          value={amount}
          onChange={(e) => {
            setAmount(e.currentTarget.value);
            setEarlier(null);
          }}
          error={trimmed && !valid ? "Enter an amount like 1500 or 1500.50" : error}
          data-autofocus
        />
        {earlier && (
          <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title="Is this the same payment?" role="alert">
            <Text size="sm">
              <Money value={earlier.amount} fw={700} inherit /> was already recorded for this flat at{" "}
              {formatDate(earlier.createdAt)}. Record another only if the flat really paid again.
            </Text>
            <Group mt="sm" gap="sm">
              <Button color="yellow.8" loading={accept.isPending} onClick={() => send(true)}>
                Yes, record it again
              </Button>
              <Button variant="default" onClick={onClose}>
                No, cancel
              </Button>
            </Group>
          </Alert>
        )}
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button
            loading={accept.isPending && !earlier}
            disabled={!valid || earlier !== null}
            onClick={() => send(false)}
          >
            Record payment
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

function RejectModal({
  claim,
  societyId,
  onClose,
}: {
  claim: PaymentClaim | null;
  societyId: number;
  onClose: () => void;
}) {
  const reject = useRejectClaim(societyId);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (claim) {
      setReason("");
      setError(null);
      reject.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when a different claim opens
  }, [claim?.id]);

  if (!claim) return <Modal opened={false} onClose={onClose} />;

  function send() {
    if (!claim || reason.trim() === "") return;
    setError(null);
    reject.mutate(
      { claimId: claim.id, reason: reason.trim() },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", title: "Not accepted", message: `Flat ${claim.flat_label}` });
          onClose();
        },
        onError: (e) =>
          setError(
            e instanceof ApiError ? (e.fieldError("reason") ?? e.message) : "Could not reject this.",
          ),
      },
    );
  }

  return (
    <Modal opened onClose={onClose} title={`Do not accept · Flat ${claim.flat_label}`} centered>
      <Stack>
        <Text size="sm">
          The resident will read your reason, so say what they should do next. Nothing is recorded
          and the flat&apos;s balance does not change.
        </Text>
        <Textarea
          label="Reason"
          placeholder="For example: I cannot see this transfer in the bank. Please send a screenshot."
          maxLength={200}
          autosize
          minRows={3}
          value={reason}
          onChange={(e) => setReason(e.currentTarget.value)}
          error={error}
          data-autofocus
        />
        <Group justify="flex-end">
          <Button variant="default" onClick={onClose}>
            Cancel
          </Button>
          <Button color="red" loading={reject.isPending} disabled={reason.trim() === ""} onClick={send}>
            Do not accept
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

/** Payments residents say they made, waiting for an office-bearer to check and record. */
export function ClaimsQueue() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const queue = useClaimQueue(societyId);
  const [accepting, setAccepting] = useState<PaymentClaim | null>(null);
  const [rejecting, setRejecting] = useState<PaymentClaim | null>(null);

  if (queue.isPending) return <CardSkeleton rows={2} />;
  if (queue.isError) return <ErrorState error={queue.error} onRetry={() => queue.refetch()} />;

  return (
    <Stack gap="xs">
      <Title order={3}>Reported by residents</Title>
      <Text size="sm" c="dimmed">
        A report changes nothing until you check the payment and record it here.
      </Text>
      {queue.data.length === 0 ? (
        <Card padding="md">
          <Group gap="sm">
            <IconInbox size={20} aria-hidden />
            <Text size="sm">Nothing is waiting to be checked.</Text>
          </Group>
        </Card>
      ) : (
        queue.data.map((claim) => {
          const mine = claim.flat === membership.flat_id;
          return (
            <Card key={claim.id} padding="md">
              <Group justify="space-between" wrap="wrap" align="flex-start" gap="sm">
                <div style={{ minWidth: 0 }}>
                  <Text fw={800}>
                    Flat {claim.flat_label} · <Money value={claim.amount} inherit />
                  </Text>
                  <Text size="sm">
                    {claim.claimed_by_name} · paid {calendarDay(claim.paid_on)} ·{" "}
                    {METHOD_LABEL[claim.method]}
                    {claim.reference ? ` · ${claim.reference}` : ""}
                  </Text>
                  <Text size="xs" c="dimmed">
                    Reported {formatDate(claim.created_at)}
                  </Text>
                </div>
                {mine ? (
                  <Text size="xs" c="dimmed">
                    Your flat: another office-bearer answers this
                  </Text>
                ) : (
                  <Group gap="xs">
                    <Button h={44} onClick={() => setAccepting(claim)}>
                      Check &amp; record
                    </Button>
                    <Button h={44} variant="default" onClick={() => setRejecting(claim)}>
                      Do not accept
                    </Button>
                  </Group>
                )}
              </Group>
            </Card>
          );
        })
      )}
      <AcceptModal claim={accepting} societyId={societyId} onClose={() => setAccepting(null)} />
      <RejectModal claim={rejecting} societyId={societyId} onClose={() => setRejecting(null)} />
    </Stack>
  );
}

/** A line on the Overview page when residents have reported payments that nobody has checked. */
export function ClaimsWaitingNotice() {
  const membership = useMembership();
  const queue = useClaimQueue(membership.society_id);
  const waiting = queue.data?.length ?? 0;
  if (waiting === 0) return null;
  return (
    <Card padding="md" bg="var(--mantine-color-yellow-light)" style={{ border: "none" }}>
      <Anchor
        component={Link}
        to={`/s/${membership.society_id}/payments`}
        c="inherit"
        fw={700}
        mih={44}
        style={{ display: "flex", alignItems: "center", gap: 8 }}
      >
        <IconInbox size={20} aria-hidden />
        {waiting === 1
          ? "1 payment reported by a resident is waiting to be checked"
          : `${waiting} payments reported by residents are waiting to be checked`}
      </Anchor>
    </Card>
  );
}
