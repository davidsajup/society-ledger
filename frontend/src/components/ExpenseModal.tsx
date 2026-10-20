import { Alert, Button, Group, Modal, Select, Stack, TextInput } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useState, type FormEvent } from "react";

import { formErrors, generalError } from "../api/client";
import { useRecordExpense } from "../api/hooks";
import type { ExpenseCategory } from "../api/types";
import { isValidAmount, normaliseAmount } from "../lib/money";

export const CATEGORIES: { value: ExpenseCategory; label: string }[] = [
  { value: "utilities", label: "Utilities" },
  { value: "repairs", label: "Repairs" },
  { value: "salaries", label: "Salaries" },
  { value: "security", label: "Security" },
  { value: "other", label: "Other" },
];

const todayLocal = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in local time

export function ExpenseModal({
  societyId,
  opened,
  onClose,
}: {
  societyId: number;
  opened: boolean;
  onClose: () => void;
}) {
  const record = useRecordExpense(societyId);
  const [category, setCategory] = useState<ExpenseCategory>("utilities");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [paidOn, setPaidOn] = useState(todayLocal());
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  useEffect(() => {
    if (opened) {
      setCategory("utilities");
      setDescription("");
      setAmount("");
      setPaidOn(todayLocal());
      setErrors({});
      setIdempotencyKey(crypto.randomUUID());
      record.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the modal opens
  }, [opened]);

  const general = generalError(errors, ["category", "description", "amount", "paid_on"]);
  const trimmed = amount.trim();
  const amountError = trimmed && !isValidAmount(trimmed) ? "Enter an amount like 1500 or 1500.50" : undefined;
  const canSubmit = isValidAmount(trimmed) && description.trim().length > 0 && paidOn !== "";

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setErrors({});
    record.mutate(
      {
        category,
        description: description.trim(),
        amount: normaliseAmount(trimmed),
        paid_on: paidOn,
        idempotencyKey,
      },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", title: "Expense recorded", message: description.trim() });
          onClose();
        },
        onError: (error) => setErrors(formErrors(error, "Could not record the expense.")),
      },
    );
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Add expense" centered>
      <form onSubmit={submit}>
        <Stack>
          <Select
            label="Category"
            data={CATEGORIES}
            value={category}
            onChange={(v) => v && setCategory(v as ExpenseCategory)}
            allowDeselect={false}
            error={errors.category}
          />
          <TextInput
            label="What was it for?"
            placeholder="Lift servicing"
            maxLength={200}
            value={description}
            onChange={(e) => setDescription(e.currentTarget.value)}
            error={errors.description}
            required
            data-autofocus
          />
          <TextInput
            label="Amount (₹)"
            inputMode="decimal"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.currentTarget.value)}
            error={amountError ?? errors.amount}
            required
          />
          <TextInput
            label="Date paid"
            type="date"
            max={todayLocal()}
            value={paidOn}
            onChange={(e) => setPaidOn(e.currentTarget.value)}
            error={errors.paid_on}
            required
          />
          {general && (
            <Alert color="red" role="alert">
              {general}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button type="submit" loading={record.isPending} disabled={!canSubmit}>
              Add expense
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
