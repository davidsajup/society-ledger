import {
  Alert,
  Badge,
  Button,
  Card,
  Code,
  CopyButton,
  Group,
  Modal,
  SegmentedControl,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import {
  IconCheck,
  IconCopy,
  IconKey,
  IconShieldLock,
  IconUserEdit,
  IconUserPlus,
} from "@tabler/icons-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { formErrors, generalError } from "../../api/client";
import {
  useAddMember,
  useChangeMember,
  useCreateLogin,
  useFlats,
  useMembers,
  useReissueLogin,
} from "../../api/hooks";
import type { IssuedLogin, LoginStatus, Member, Role } from "../../api/types";
import { useMembership, useSession } from "../../auth/session";
import { CardSkeleton, EmptyState, ErrorState } from "../../components/common";
import { ConfirmModal } from "../../components/ConfirmModal";
import { calendarDay } from "../../lib/dates";
import { ROLE_LABEL, ROLE_OPTIONS } from "../../lib/capabilities";

const ROLE_COLOR: Record<Role, string> = {
  president: "violet",
  secretary: "indigo",
  treasurer: "teal",
  resident: "sunrise",
};
const STATUS: Record<Exclude<LoginStatus, "active">, { label: string; color: string }> = {
  temporary: { label: "Not signed in yet", color: "yellow" },
  expired: { label: "Password expired", color: "red" },
};

type FlatOption = { value: string; label: string };

export function ResidentsPage() {
  const societyId = useMembership().society_id;
  const { me } = useSession();
  const members = useMembers(societyId);
  const flats = useFlats(societyId);
  const reissue = useReissueLogin(societyId);
  const [adding, setAdding] = useState(false);
  const [changing, setChanging] = useState<Member | null>(null);
  const [issued, setIssued] = useState<{ login: IssuedLogin; person: string } | null>(null);
  const [resetting, setResetting] = useState<Member | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  const flatLabel = useMemo(
    () => new Map((flats.data ?? []).map((f) => [f.id, f.label])),
    [flats.data],
  );
  const flatOptions: FlatOption[] = (flats.data ?? []).map((f) => ({
    value: String(f.id),
    label: `Flat ${f.label}`,
  }));

  if (members.isPending || flats.isPending) return <CardSkeleton rows={5} />;
  if (members.isError) return <ErrorState error={members.error} onRetry={() => members.refetch()} />;
  if (flats.isError) return <ErrorState error={flats.error} onRetry={() => flats.refetch()} />;

  function confirmReset() {
    if (!resetting) return;
    setResetError(null);
    reissue.mutate(resetting.id, {
      onSuccess: (login) => {
        setIssued({ login, person: resetting.name || resetting.user });
        setResetting(null);
      },
      onError: (error) =>
        setResetError(
          Object.values(formErrors(error, "Could not issue a new password."))[0] ??
            "Could not issue a new password.",
        ),
    });
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between">
        <Title order={3}>People &amp; roles</Title>
        <Button leftSection={<IconUserPlus size={18} />} onClick={() => setAdding(true)}>
          Add person
        </Button>
      </Group>

      {members.data.length === 0 ? (
        <EmptyState title="No members yet" />
      ) : (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
          {members.data.map((member) => {
            const status = member.login_status === "active" ? null : STATUS[member.login_status];
            const isMe = member.user === me.username;
            return (
              <Card key={member.id} padding="md">
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <div style={{ minWidth: 0 }}>
                    <Text fw={800} truncate>
                      {member.name || member.user}
                      {isMe && (
                        <Text span c="dimmed" fw={500}>
                          {" "}
                          (you)
                        </Text>
                      )}
                    </Text>
                    <Text size="sm" c="dimmed" truncate>
                      {member.flat !== null
                        ? `Flat ${flatLabel.get(member.flat) ?? member.flat}`
                        : "No flat"}
                    </Text>
                    <Text size="xs" c="dimmed" truncate>
                      {member.user}
                    </Text>
                  </div>
                  <Stack gap={4} align="flex-end">
                    <Badge variant="light" color={ROLE_COLOR[member.role]}>
                      {ROLE_LABEL[member.role]}
                    </Badge>
                    {status && (
                      <Badge variant="light" color={status.color} size="sm">
                        {status.label}
                      </Badge>
                    )}
                    {/* Nobody changes their own role or flat; another office-bearer does it. */}
                    {!isMe && (
                      <Group gap={4} wrap="nowrap">
                        <Button
                          size="compact-xs"
                          variant="subtle"
                          color="gray"
                          leftSection={<IconUserEdit size={14} />}
                          onClick={() => setChanging(member)}
                        >
                          Change
                        </Button>
                        <Button
                          size="compact-xs"
                          variant="subtle"
                          color="gray"
                          leftSection={<IconKey size={14} />}
                          onClick={() => {
                            setResetError(null);
                            setResetting(member);
                          }}
                        >
                          New password
                        </Button>
                      </Group>
                    )}
                  </Stack>
                </Group>
              </Card>
            );
          })}
        </SimpleGrid>
      )}

      <AddPersonModal
        societyId={societyId}
        opened={adding}
        onClose={() => setAdding(false)}
        onIssued={(login, person) => {
          setAdding(false);
          setIssued({ login, person });
        }}
        flats={flatOptions}
      />

      <ChangeMemberModal
        societyId={societyId}
        member={changing}
        flats={flatOptions}
        onClose={() => setChanging(null)}
      />

      <ConfirmModal
        opened={resetting !== null}
        title="Issue a new password?"
        confirmLabel="Issue new password"
        loading={reissue.isPending}
        error={resetError}
        onConfirm={confirmReset}
        onClose={() => setResetting(null)}
      >
        {resetting && (
          <>
            This replaces {resetting.name || resetting.user}&apos;s password with a new temporary one
            and signs them out everywhere. They will have to choose their own password again.
          </>
        )}
      </ConfirmModal>

      <CredentialsDialog issued={issued} onDone={() => setIssued(null)} />
    </Stack>
  );
}

/** Shows a temporary password exactly once. The server cannot show it again, and neither can we. */
function CredentialsDialog({
  issued,
  onDone,
}: {
  issued: { login: IssuedLogin; person: string } | null;
  onDone: () => void;
}) {
  const login = issued?.login;
  const expires = login ? calendarDay(login.expires_at) : "";
  const details = login
    ? `Username: ${login.username}\nTemporary password: ${login.temp_password}\nValid until ${expires}. You will be asked to choose your own password at first login.`
    : "";

  return (
    <Modal
      opened={issued !== null}
      onClose={onDone}
      closeOnClickOutside={false}
      closeOnEscape={false}
      withCloseButton={false}
      title={`Login details for ${issued?.person ?? ""}`}
      centered
    >
      {login && (
        <Stack gap="md">
          <Alert color="yellow" icon={<IconShieldLock size={18} />} title="Shown only once">
            Give these to {issued.person} privately. The password cannot be shown again; if it is
            lost, issue a new one.
          </Alert>

          <div>
            <Text size="sm" c="dimmed">
              Username
            </Text>
            <Code fz="md" block>
              {login.username}
            </Code>
          </div>
          <div>
            <Text size="sm" c="dimmed">
              Temporary password
            </Text>
            <Code fz="lg" fw={700} block>
              {login.temp_password}
            </Code>
          </div>
          <Text size="sm" c="dimmed">
            Valid until {expires}. They must choose their own password the first time they sign in.
          </Text>

          <Group justify="space-between">
            <CopyButton value={details}>
              {({ copied, copy }) => (
                <Button
                  variant="light"
                  leftSection={copied ? <IconCheck size={16} /> : <IconCopy size={16} />}
                  onClick={copy}
                >
                  {copied ? "Copied" : "Copy login details"}
                </Button>
              )}
            </CopyButton>
            <Button onClick={onDone}>I&apos;ve saved it</Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}

type Mode = "create" | "link";

/** Role + flat inputs shared by "add" and "change": the flat is required only for residents. */
function RoleAndFlat({
  role,
  setRole,
  flat,
  setFlat,
  flats,
  errors,
}: {
  role: Role;
  setRole: (role: Role) => void;
  flat: string | null;
  setFlat: (flat: string | null) => void;
  flats: FlatOption[];
  errors: Record<string, string>;
}) {
  const required = role === "resident";
  return (
    <>
      <Select
        label="Role"
        data={ROLE_OPTIONS}
        value={role}
        onChange={(v) => v && setRole(v as Role)}
        allowDeselect={false}
        error={errors.role}
      />
      <Select
        label="Flat they live in"
        description={
          required
            ? undefined
            : "Optional. Office-bearers are residents too and pay their own dues."
        }
        placeholder="Choose a flat"
        data={flats}
        value={flat}
        onChange={setFlat}
        searchable
        clearable={!required}
        error={errors.flat}
        required={required}
      />
    </>
  );
}

function AddPersonModal({
  societyId,
  opened,
  onClose,
  onIssued,
  flats,
}: {
  societyId: number;
  opened: boolean;
  onClose: () => void;
  onIssued: (login: IssuedLogin, person: string) => void;
  flats: FlatOption[];
}) {
  const create = useCreateLogin(societyId);
  const link = useAddMember(societyId);
  const [mode, setMode] = useState<Mode>("create");
  const [name, setName] = useState("");
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<Role>("resident");
  const [flat, setFlat] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (opened) {
      setMode("create");
      setName("");
      setUsername("");
      setRole("resident");
      setFlat(null);
      setErrors({});
      create.reset();
      link.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the modal opens
  }, [opened]);

  const who = mode === "create" ? name.trim() : username.trim();
  const canSubmit = who !== "" && (role !== "resident" || flat !== null);
  const general = generalError(errors, ["name", "username", "role", "flat"]);
  const busy = create.isPending || link.isPending;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setErrors({});
    const flatId = flat ? Number(flat) : null;
    if (mode === "create") {
      create.mutate(
        { name: name.trim(), role, flat: flatId },
        {
          onSuccess: (login) => onIssued(login, name.trim()),
          onError: (error) => setErrors(formErrors(error, "Could not create the login.")),
        },
      );
    } else {
      link.mutate(
        { username: username.trim(), role, flat: flatId },
        {
          onSuccess: () => {
            notifications.show({
              color: "teal",
              title: "Added",
              message: `${username.trim()} is now ${ROLE_LABEL[role].toLowerCase()}`,
            });
            onClose();
          },
          onError: (error) => setErrors(formErrors(error, "Could not add this person.")),
        },
      );
    }
  }

  return (
    <Modal opened={opened} onClose={onClose} title="Add a person to this society" centered>
      <form onSubmit={submit}>
        <Stack>
          <SegmentedControl
            fullWidth
            value={mode}
            onChange={(v) => {
              setMode(v as Mode);
              setErrors({});
            }}
            data={[
              { value: "create", label: "Create a login" },
              { value: "link", label: "Existing login" },
            ]}
          />

          {mode === "create" ? (
            <TextInput
              label="Full name"
              description="We create their username and a one-time password for you to hand over."
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
              error={errors.name}
              required
              data-autofocus
            />
          ) : (
            <TextInput
              label="Username"
              description="They must already have a login (for example from another society)."
              autoCapitalize="none"
              value={username}
              onChange={(e) => setUsername(e.currentTarget.value)}
              error={errors.username}
              required
              data-autofocus
            />
          )}

          <RoleAndFlat
            role={role}
            setRole={setRole}
            flat={flat}
            setFlat={setFlat}
            flats={flats}
            errors={errors}
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
            <Button type="submit" loading={busy} disabled={!canSubmit}>
              {mode === "create" ? "Create login" : "Add"}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

/** Change someone's role and/or flat. Only what actually changed is sent. */
function ChangeMemberModal({
  societyId,
  member,
  flats,
  onClose,
}: {
  societyId: number;
  member: Member | null;
  flats: FlatOption[];
  onClose: () => void;
}) {
  const change = useChangeMember(societyId);
  const [role, setRole] = useState<Role>("resident");
  const [flat, setFlat] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (member) {
      setRole(member.role);
      setFlat(member.flat === null ? null : String(member.flat));
      setErrors({});
      change.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when a member is chosen
  }, [member?.id]);

  if (!member) return <Modal opened={false} onClose={onClose} />;

  const originalFlat = member.flat === null ? null : String(member.flat);
  const changed = role !== member.role || flat !== originalFlat;
  const general = generalError(errors, ["role", "flat"]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!member || !changed) return;
    setErrors({});
    change.mutate(
      {
        memberId: member.id,
        ...(role !== member.role ? { role } : {}),
        ...(flat !== originalFlat ? { flat: flat === null ? null : Number(flat) } : {}),
      },
      {
        onSuccess: () => {
          notifications.show({
            color: "teal",
            title: "Updated",
            message: `${member.name || member.user} is now ${ROLE_LABEL[role].toLowerCase()}`,
          });
          onClose();
        },
        onError: (error) => setErrors(formErrors(error, "Could not change this person.")),
      },
    );
  }

  return (
    <Modal opened onClose={onClose} title={`Change ${member.name || member.user}`} centered>
      <form onSubmit={submit}>
        <Stack>
          <RoleAndFlat
            role={role}
            setRole={setRole}
            flat={flat}
            setFlat={setFlat}
            flats={flats}
            errors={errors}
          />
          <Text size="xs" c="dimmed">
            Takes effect immediately. The change is recorded in the activity log.
          </Text>
          {general && (
            <Alert color="red" role="alert">
              {general}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button
              type="submit"
              loading={change.isPending}
              disabled={!changed || (role === "resident" && flat === null)}
            >
              Save
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
