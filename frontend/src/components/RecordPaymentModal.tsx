import { Button, Group, Modal, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { useRecordPayment } from "../api/hooks";
import { isValidAmount, normaliseAmount, toCents } from "../lib/money";
import { Money } from "./common";

export interface PayableFlat {
  id: number;
  label: string;
  outstanding: string;
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
  // One key per opening of the form. If the request is retried (double tap, flaky network),
  // the server sees the same key and records the payment once.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    if (flat) {
      setAmount("");
      setNote("");
      setServerError(null);
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

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!flat || !isValidAmount(trimmed) || tooMuch) return;
    setServerError(null);
    record.mutate(
      { flatId: flat.id, amount: normaliseAmount(trimmed), note: note.trim(), idempotencyKey },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", title: "Payment recorded", message: `Flat ${flat.label}` });
          onClose();
        },
        onError: (error) =>
          setServerError(
            error instanceof ApiError
              ? (error.fieldError("amount") ?? error.message)
              : "Could not record the payment.",
          ),
      },
    );
  }

  return (
    <Modal opened onClose={onClose} title={`Record payment · Flat ${flat.label}`} centered>
      <form onSubmit={submit}>
        <Stack>
          <Text size="sm" c="dimmed">
            Currently owes <Money value={flat.outstanding} fw={800} inherit c="var(--mantine-color-text)" />
          </Text>
          <TextInput
            label="Amount received (₹)"
            inputMode="decimal"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.currentTarget.value)}
            error={clientError ?? serverError}
            data-autofocus
            required
            rightSectionWidth={86}
            rightSection={
              <Button
                size="compact-xs"
                variant="light"
                onClick={() => setAmount(flat.outstanding)}
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
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button
              type="submit"
              loading={record.isPending}
              disabled={!isValidAmount(trimmed) || tooMuch}
            >
              Record payment
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
