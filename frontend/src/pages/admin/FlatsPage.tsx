import {
  Alert,
  Button,
  Card,
  Group,
  Modal,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconPencil, IconPlus } from "@tabler/icons-react";
import { useEffect, useState, type FormEvent } from "react";

import { formErrors, generalError } from "../../api/client";
import { useFlats, useSaveFlat } from "../../api/hooks";
import type { Flat } from "../../api/types";
import { useMembership } from "../../auth/session";
import { CardSkeleton, EmptyState, ErrorState, Money } from "../../components/common";
import { isValidAmount, normaliseAmount, toCents } from "../../lib/money";

type Editing = { mode: "new" } | { mode: "edit"; flat: Flat } | null;

export function FlatsPage() {
  const societyId = useMembership().society_id;
  const flats = useFlats(societyId);
  const [editing, setEditing] = useState<Editing>(null);

  if (flats.isPending) return <CardSkeleton rows={5} />;
  if (flats.isError) return <ErrorState error={flats.error} onRetry={() => flats.refetch()} />;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={3}>Flats</Title>
        <Button leftSection={<IconPlus size={18} />} onClick={() => setEditing({ mode: "new" })}>
          Add flat
        </Button>
      </Group>
      <Text size="sm" c="dimmed">
        The monthly amount is what the billing job charges each flat on the 1st. A flat set to ₹0 is
        not billed.
      </Text>

      {flats.data.length === 0 ? (
        <EmptyState title="No flats yet">Add your first flat to get started.</EmptyState>
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          {flats.data.map((flat) => (
            <Card key={flat.id} padding="md">
              <Group justify="space-between" wrap="nowrap">
                <div>
                  <Text fw={800}>Flat {flat.label}</Text>
                  <Text size="sm" c="dimmed">
                    {toCents(flat.monthly_maintenance) > 0n ? (
                      <>
                        <Money value={flat.monthly_maintenance} /> / month
                      </>
                    ) : (
                      "Not billed"
                    )}
                  </Text>
                </div>
                <Button
                  size="compact-md"
                  variant="light"
                  leftSection={<IconPencil size={16} />}
                  onClick={() => setEditing({ mode: "edit", flat })}
                >
                  Edit
                </Button>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      )}

      <FlatModal societyId={societyId} editing={editing} onClose={() => setEditing(null)} />
    </Stack>
  );
}

function FlatModal({
  societyId,
  editing,
  onClose,
}: {
  societyId: number;
  editing: Editing;
  onClose: () => void;
}) {
  const save = useSaveFlat(societyId);
  const [label, setLabel] = useState("");
  const [amount, setAmount] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (editing) {
      setLabel(editing.mode === "edit" ? editing.flat.label : "");
      setAmount(editing.mode === "edit" ? editing.flat.monthly_maintenance : "0.00");
      setErrors({});
      save.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the modal (re)opens
  }, [editing]);

  const general = generalError(errors, ["label", "monthly_maintenance"]);
  const amountOk = /^\d+(\.\d{1,2})?$/.test(amount.trim()) && (amount.trim() === "0" || amount.trim() === "0.00" || isValidAmount(amount.trim()));

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!editing || !amountOk || !label.trim()) return;
    save.mutate(
      {
        id: editing.mode === "edit" ? editing.flat.id : undefined,
        label: label.trim(),
        monthly_maintenance: normaliseAmount(amount.trim()),
      },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", title: "Flat saved", message: label.trim() });
          onClose();
        },
        onError: (error) => setErrors(formErrors(error, "Could not save the flat.")),
      },
    );
  }

  return (
    <Modal
      opened={editing !== null}
      onClose={onClose}
      title={editing?.mode === "edit" ? `Edit flat ${editing.flat.label}` : "Add flat"}
      centered
    >
      <form onSubmit={submit}>
        <Stack>
          <TextInput
            label="Flat number"
            placeholder="A-101"
            maxLength={20}
            value={label}
            onChange={(e) => setLabel(e.currentTarget.value)}
            error={errors.label}
            required
            data-autofocus
          />
          <TextInput
            label="Monthly maintenance (₹)"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.currentTarget.value)}
            error={errors.monthly_maintenance ?? (amount && !amountOk ? "Enter an amount like 1500 or 1500.50" : undefined)}
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
            <Button type="submit" loading={save.isPending} disabled={!amountOk || !label.trim()}>
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
