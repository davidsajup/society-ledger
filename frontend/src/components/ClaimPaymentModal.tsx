import { Alert, Button, Group, Modal, Select, Stack, Text, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState, type FormEvent } from "react";

import { formErrors, generalError } from "../api/client";
import { useSubmitClaim } from "../api/hooks";
import type { ClaimMethod } from "../api/types";
import { isValidAmount, normaliseAmount, toCents } from "../lib/money";
import { METHOD_OPTIONS, todayIso } from "./claims";
import { Money } from "./common";

/**
 * "I have paid": tell the treasurer about a payment made outside the app. This changes no balance.
 * The treasurer checks it and records the real payment, and the answer shows up on the dashboard.
 */
export function ClaimPaymentModal({
  opened,
  societyId,
  flatId,
  flatLabel,
  outstanding,
  onClose,
}: {
  opened: boolean;
  societyId: number;
  flatId: number;
  flatLabel: string;
  outstanding: string;
  onClose: () => void;
}) {
  const submitClaim = useSubmitClaim(societyId, flatId);
  const [amount, setAmount] = useState("");
  const [paidOn, setPaidOn] = useState(todayIso());
  const [method, setMethod] = useState<ClaimMethod>("upi");
  const [reference, setReference] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  // One key per opening of the form: a double tap sends the same key and makes one claim.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    if (opened) {
      setAmount("");
      setPaidOn(todayIso());
      setMethod("upi");
      setReference("");
      setErrors({});
      setIdempotencyKey(crypto.randomUUID());
      submitClaim.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the form opens
  }, [opened]);

  const trimmed = amount.trim();
  const tooMuch = isValidAmount(trimmed) && toCents(trimmed) > toCents(outstanding);
  const clientError =
    trimmed && !isValidAmount(trimmed)
      ? "Enter an amount like 1500 or 1500.50"
      : tooMuch
        ? "That is more than your flat owes."
        : null;
  const canSend = isValidAmount(trimmed) && !tooMuch && paidOn !== "" && paidOn <= todayIso();
  const general = generalError(errors, ["amount", "paid_on", "method", "reference"]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSend) return;
    setErrors({});
    submitClaim.mutate(
      {
        amount: normaliseAmount(trimmed),
        paid_on: paidOn,
        method,
        reference: reference.trim(),
        idempotencyKey,
      },
      {
        onSuccess: () => {
          notifications.show({
            color: "teal",
            title: "Sent to the treasurer",
            message: `Flat ${flatLabel}: you will see it here once it is checked`,
          });
          onClose();
        },
        onError: (error) => setErrors(formErrors(error, "Could not send this. Please try again.")),
      },
    );
  }

  return (
    <Modal opened={opened} onClose={onClose} title={`I have paid · Flat ${flatLabel}`} centered>
      <form onSubmit={submit}>
        <Stack>
          <Text size="sm" c="dimmed">
            Your flat owes <Money value={outstanding} fw={800} inherit c="var(--mantine-color-text)" />.
            This does not change your balance. The treasurer checks the payment and records it, and
            you will see the result on this page.
          </Text>
          <TextInput
            label="Amount you paid (₹)"
            inputMode="decimal"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.currentTarget.value)}
            error={clientError ?? errors.amount}
            data-autofocus
            required
            rightSectionWidth={86}
            rightSection={
              <Button h={40} variant="light" type="button" onClick={() => setAmount(outstanding)}>
                Full amount
              </Button>
            }
          />
          <TextInput
            label="Date you paid"
            type="date"
            value={paidOn}
            max={todayIso()}
            onChange={(e) => setPaidOn(e.currentTarget.value)}
            error={errors.paid_on}
            required
          />
          <Select
            label="How you paid"
            data={METHOD_OPTIONS}
            value={method}
            onChange={(v) => v && setMethod(v as ClaimMethod)}
            allowDeselect={false}
            error={errors.method}
          />
          <TextInput
            label="Reference (optional)"
            description="A UPI transaction number, cheque number or receipt number helps the treasurer find it."
            maxLength={60}
            value={reference}
            onChange={(e) => setReference(e.currentTarget.value)}
            error={errors.reference}
          />
          {general && (
            <Alert color="red" role="alert">
              {general}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" type="button" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" loading={submitClaim.isPending} disabled={!canSend}>
              Send to the treasurer
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
