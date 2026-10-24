import { Alert, Button, Group, Modal, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useEffect, useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { useRecordPayment } from "../api/hooks";
import { timeLabel } from "../lib/dates";
import { isValidAmount, normaliseAmount, toCents } from "../lib/money";
import { Money } from "./common";

export interface PayableFlat {
  id: number;
  label: string;
  outstanding: string;
}

/** What the server sends with a 409 `possible_duplicate`: the payment recorded moments ago. */
interface EarlierPayment {
  amount: string;
  createdAt: string;
}

function earlierPaymentFrom(error: unknown): EarlierPayment | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const data = error.data as { code?: string; previous?: { amount: string; created_at: string } };
  if (data?.code !== "possible_duplicate" || !data.previous) return null;
  return { amount: data.previous.amount, createdAt: data.previous.created_at };
}

export function RecordPaymentModal({
  societyId,
  flat,
  onClose,
}: {
  societyId: number;
  flat: PayableFlat | null;
  onClose: () => void;
}) {
  const record = useRecordPayment(societyId);
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [serverError, setServerError] = useState<string | null>(null);
  const [earlier, setEarlier] = useState<EarlierPayment | null>(null);
  // One key per opening of the form. If the request is retried (double tap, flaky network),
  // the server sees the same key and records the payment once.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    if (flat) {
      setAmount("");
      setNote("");
      setServerError(null);
      setEarlier(null);
      setIdempotencyKey(crypto.randomUUID());
      record.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when a different flat opens
  }, [flat?.id]);

  if (!flat) return <Modal opened={false} onClose={onClose} />;

  const trimmed = amount.trim();
  const tooMuch = isValidAmount(trimmed) && toCents(trimmed) > toCents(flat.outstanding);
  const clientError = trimmed && !isValidAmount(trimmed)
    ? "Enter an amount like 1500 or 1500.50"
    : tooMuch
      ? "That is more than the flat owes."
      : null;

  function send(confirmDuplicate: boolean) {
    if (!flat || !isValidAmount(trimmed) || tooMuch) return;
    setServerError(null);
    setEarlier(null);
    record.mutate(
      {
        flatId: flat.id,
        amount: normaliseAmount(trimmed),
        note: note.trim(),
        idempotencyKey,
        confirmDuplicate,
      },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", title: "Payment recorded", message: `Flat ${flat.label}` });
          onClose();
        },
        onError: (error) => {
          // The server wrote nothing. The same key is safe to reuse: only a stored payment uses it.
          const duplicate = earlierPaymentFrom(error);
          if (duplicate) return setEarlier(duplicate);
          setServerError(
            error instanceof ApiError
              ? (error.fieldError("amount") ?? error.message)
              : "Could not record the payment.",
          );
        },
      },
    );
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    send(false);
  }

  return (
    <Modal opened onClose={onClose} title={`Record payment · Flat ${flat.label}`} centered>
      <form onSubmit={submit}>
        <Stack>
          <Text size="sm" c="dimmed">
            Currently owes <Money value={flat.outstanding} fw={800} inherit c="var(--mantine-color-text)" />
          </Text>
          <Text size="sm" c="dimmed">
            This adds the payment to the society&apos;s books. If you make a mistake, you can reverse it
            later; it is never erased.
          </Text>
          <TextInput
            label="Amount received (₹)"
            inputMode="decimal"
            placeholder="0.00"
            value={amount}
            onChange={(e) => {
              setAmount(e.currentTarget.value);
              setEarlier(null); // a different amount is a different question
            }}
            error={clientError ?? serverError}
            data-autofocus
            required
            rightSectionWidth={86}
            rightSection={
              <Button
                h={40}
                variant="light"
                onClick={() => {
                  setAmount(flat.outstanding);
                  setEarlier(null);
                }}
                type="button"
              >
                Full amount
              </Button>
            }
          />
          <TextInput
            label="Note (optional)"
            placeholder="Cheque no., UPI ref…"
            maxLength={200}
            value={note}
            onChange={(e) => setNote(e.currentTarget.value)}
          />
          {earlier && (
            <Alert
              color="yellow"
              icon={<IconAlertTriangle size={18} />}
              title="Is this the same payment?"
              role="alert"
            >
              <Text size="sm">
                <Money value={earlier.amount} fw={700} inherit /> was already recorded for this flat
                at {timeLabel(earlier.createdAt)}. Record another one only if the flat really paid
                again.
              </Text>
              <Group mt="sm" gap="sm">
                <Button
                  color="yellow.8"
                  loading={record.isPending}
                  onClick={() => send(true)}
                  type="button"
                >
                  Yes, record it again
                </Button>
                <Button variant="default" onClick={onClose} type="button">
                  No, cancel
                </Button>
              </Group>
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button
              type="submit"
              loading={record.isPending}
              disabled={!isValidAmount(trimmed) || tooMuch || earlier !== null}
            >
              Record payment
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
