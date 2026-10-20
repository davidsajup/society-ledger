import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconUserPlus } from "@tabler/icons-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { formErrors, generalError } from "../../api/client";
import { useAddMember, useFlats, useMembers } from "../../api/hooks";
import type { Role } from "../../api/types";
import { useMembership } from "../../auth/session";
import { CardSkeleton, EmptyState, ErrorState } from "../../components/common";

const ROLE_COLOR: Record<Role, string> = { admin: "violet", treasurer: "teal", resident: "sunrise" };

export function ResidentsPage() {
  const societyId = useMembership().society_id;
  const members = useMembers(societyId);
  const flats = useFlats(societyId);
  const [adding, setAdding] = useState(false);

  const flatLabel = useMemo(
    () => new Map((flats.data ?? []).map((f) => [f.id, f.label])),
    [flats.data],
  );

  if (members.isPending || flats.isPending) return <CardSkeleton rows={5} />;
  if (members.isError) return <ErrorState error={members.error} onRetry={() => members.refetch()} />;
  if (flats.isError) return <ErrorState error={flats.error} onRetry={() => flats.refetch()} />;

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={3}>Residents &amp; roles</Title>
        <Button leftSection={<IconUserPlus size={18} />} onClick={() => setAdding(true)}>
          Add person
        </Button>
      </Group>

      {members.data.length === 0 ? (
        <EmptyState title="No members yet" />
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          {members.data.map((member) => (
            <Card key={member.id} padding="md">
              <Group justify="space-between" wrap="nowrap">
                <div>
                  <Text fw={800}>{member.user}</Text>
                  <Text size="sm" c="dimmed">
                    {member.flat !== null ? `Flat ${flatLabel.get(member.flat) ?? member.flat}` : "Society-wide role"}
                  </Text>
                </div>
                <Badge variant="light" color={ROLE_COLOR[member.role]} tt="capitalize">
                  {member.role}
                </Badge>
              </Group>
            </Card>
          ))}
        </SimpleGrid>
      )}

      <AddMemberModal
        societyId={societyId}
        opened={adding}
        onClose={() => setAdding(false)}
        flats={(flats.data ?? []).map((f) => ({ value: String(f.id), label: `Flat ${f.label}` }))}
      />
    </Stack>
  );
}

function AddMemberModal({
  societyId,
  opened,
  onClose,
  flats,
}: {
  societyId: number;
  opened: boolean;
  onClose: () => void;
  flats: { value: string; label: string }[];
}) {
  const add = useAddMember(societyId);
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<Role>("resident");
  const [flat, setFlat] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (opened) {
      setUsername("");
      setRole("resident");
      setFlat(null);
      setErrors({});
      add.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the modal opens
  }, [opened]);

  const general = generalError(errors, ["username", "role", "flat"]);
  const needsFlat = role === "resident";
  const canSubmit = username.trim() !== "" && (!needsFlat || flat !== null);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    add.mutate(
      { username: username.trim(), role, flat: needsFlat && flat ? Number(flat) : null },
      {
        onSuccess: () => {
          notifications.show({ color: "teal", title: "Added", message: `${username.trim()} is now ${role}` });
          onClose();
        },
        onError: (error) => setErrors(formErrors(error, "Could not add this person.")),
      },
    );
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Add a person to this society" centered>
      <form onSubmit={submit}>
        <Stack>
          <TextInput
            label="Username"
            description="They must already have a login."
            autoCapitalize="none"
            value={username}
            onChange={(e) => setUsername(e.currentTarget.value)}
            error={errors.username}
            required
            data-autofocus
          />
          <Select
            label="Role"
            data={[
              { value: "resident", label: "Resident" },
              { value: "treasurer", label: "Treasurer" },
              { value: "admin", label: "Admin" },
            ]}
            value={role}
            onChange={(v) => v && setRole(v as Role)}
            allowDeselect={false}
            error={errors.role}
          />
          {needsFlat && (
            <Select
              label="Flat"
              placeholder="Choose a flat"
              data={flats}
              value={flat}
              onChange={setFlat}
              searchable
              error={errors.flat}
              required
            />
          )}
          {general && (
            <Alert color="red" role="alert">
              {general}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button type="submit" loading={add.isPending} disabled={!canSubmit}>
              Add
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
