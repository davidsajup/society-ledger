import {
  Alert,
  Avatar,
  Badge,
  Box,
  Button,
  Card,
  Container,
  Group,
  Menu,
  Modal,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { IconBuildingEstate, IconKey, IconLogout, IconPlus } from "@tabler/icons-react";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { formErrors, generalError } from "../../api/client";
import {
  useCreateSociety,
  useLogout,
  usePlatformSocieties,
  useReissueManager,
} from "../../api/hooks";
import type { IssuedLogin, LoginStatus, PlatformManager, PlatformSociety } from "../../api/types";
import { useSession } from "../../auth/session";
import { CardSkeleton, EmptyState, ErrorState } from "../../components/common";
import { ConfirmModal } from "../../components/ConfirmModal";
import { CredentialsDialog } from "../../components/CredentialsDialog";
import { ROLE_LABEL } from "../../lib/capabilities";

const STATUS: Record<Exclude<LoginStatus, "active">, { label: string; color: string }> = {
  temporary: { label: "Not signed in yet", color: "yellow" },
  expired: { label: "Password expired", color: "red" },
};

/** "Green Meadows" -> "green-meadows": what the society's usernames and URLs are built from. */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 50);
}

type Issued = { login: IssuedLogin; person: string; hint?: string };

/**
 * The super admin's home. Onboarding only: create a society and hand its president a login;
 * reissue a lost president/secretary login. There is no money anywhere on this page, by design.
 */
export function PlatformPage() {
  const { me } = useSession();
  const societies = usePlatformSocieties();
  const reissue = useReissueManager();
  const logout = useLogout();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const [issued, setIssued] = useState<Issued | null>(null);
  const [resetting, setResetting] = useState<{ society: PlatformSociety; manager: PlatformManager } | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  function confirmReset() {
    if (!resetting) return;
    setResetError(null);
    reissue.mutate(
      { societyId: resetting.society.id, memberId: resetting.manager.member_id },
      {
        onSuccess: (login) => {
          setIssued({ login, person: resetting.manager.name || resetting.manager.username });
          setResetting(null);
        },
        onError: (error) =>
          setResetError(
            Object.values(formErrors(error, "Could not issue a new password."))[0] ??
              "Could not issue a new password.",
          ),
      },
    );
  }

  return (
    <Box mih="100dvh">
      <Paper component="header" radius={0} withBorder px="md" py="sm">
        <Container size="md" p={0}>
          <Group justify="space-between" wrap="nowrap">
            <Group gap="xs" wrap="nowrap" miw={0}>
              <IconBuildingEstate color="var(--mantine-color-sunrise-7)" />
              <div style={{ minWidth: 0 }}>
                <Text fw={800} lh={1.1} truncate>
                  Society Ledger
                </Text>
                <Text size="xs" c="dimmed">
                  Super admin
                </Text>
              </div>
            </Group>
            <Menu position="bottom-end" width={220}>
              <Menu.Target>
                <UnstyledButton
                  aria-label="Account menu"
                  h={44}
                  w={44}
                  style={{ display: "grid", placeItems: "center" }}
                >
                  <Avatar color="sunrise" radius="xl" size="md">
                    {me.username.slice(0, 1).toUpperCase()}
                  </Avatar>
                </UnstyledButton>
              </Menu.Target>
              <Menu.Dropdown>
                <Menu.Label>Signed in as {me.username}</Menu.Label>
                <Menu.Item
                  leftSection={<IconKey size={16} />}
                  onClick={() => navigate("/change-password")}
                >
                  Change password
                </Menu.Item>
                <Menu.Item
                  color="red"
                  leftSection={<IconLogout size={16} />}
                  onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login") })}
                >
                  Log out
                </Menu.Item>
              </Menu.Dropdown>
            </Menu>
          </Group>
        </Container>
      </Paper>

      <Container size="md" py="lg">
        <Stack gap="lg">
          <Group justify="space-between" align="flex-end">
            <div>
              <Title order={2}>Societies</Title>
              <Text size="sm" c="dimmed">
                Create a society and give its president the first login. The president then adds
                flats and everyone else.
              </Text>
            </div>
            <Button leftSection={<IconPlus size={18} />} onClick={() => setCreating(true)}>
              New society
            </Button>
          </Group>

          {societies.isPending ? (
            <CardSkeleton rows={3} />
          ) : societies.isError ? (
            <ErrorState error={societies.error} onRetry={() => societies.refetch()} />
          ) : societies.data.length === 0 ? (
            <EmptyState title="No societies yet">Use New society to create the first one.</EmptyState>
          ) : (
            <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
              {societies.data.map((society) => (
                <Card key={society.id} padding="md">
                  <Text fw={800}>{society.name}</Text>
                  <Text size="sm" c="dimmed">
                    {society.slug} · {society.flat_count}{" "}
                    {society.flat_count === 1 ? "flat" : "flats"} · {society.member_count}{" "}
                    {society.member_count === 1 ? "person" : "people"}
                  </Text>
                  <Stack gap="xs" mt="sm">
                    {society.managers.map((manager) => {
                      const status =
                        manager.login_status === "active" ? null : STATUS[manager.login_status];
                      return (
                        <Group key={manager.member_id} justify="space-between" wrap="nowrap">
                          <div style={{ minWidth: 0 }}>
                            <Text size="sm" fw={700} truncate>
                              {manager.name || manager.username}
                            </Text>
                            <Group gap={6}>
                              <Badge variant="light">{ROLE_LABEL[manager.role]}</Badge>
                              {status && (
                                <Badge variant="light" color={status.color}>
                                  {status.label}
                                </Badge>
                              )}
                            </Group>
                          </div>
                          <Button
                            variant="light"
                            color="gray"
                            aria-label={`New password for ${manager.name || manager.username}`}
                            onClick={() => {
                              setResetError(null);
                              setResetting({ society, manager });
                            }}
                          >
                            New password
                          </Button>
                        </Group>
                      );
                    })}
                  </Stack>
                </Card>
              ))}
            </SimpleGrid>
          )}
        </Stack>
      </Container>

      <NewSocietyModal
        opened={creating}
        onClose={() => setCreating(false)}
        onCreated={(login, person) => {
          setCreating(false);
          setIssued({
            login,
            person,
            hint: "Hand these to the president. After choosing a password they can add flats and everyone else from the People page.",
          });
        }}
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
            This replaces {resetting.manager.name || resetting.manager.username}&apos;s password
            with a new temporary one and signs them out everywhere.
          </>
        )}
      </ConfirmModal>

      <CredentialsDialog issued={issued} hint={issued?.hint} onDone={() => setIssued(null)} />
    </Box>
  );
}

function NewSocietyModal({
  opened,
  onClose,
  onCreated,
}: {
  opened: boolean;
  onClose: () => void;
  onCreated: (login: IssuedLogin, president: string) => void;
}) {
  const create = useCreateSociety();
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [president, setPresident] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (opened) {
      setName("");
      setSlug("");
      setSlugEdited(false);
      setPresident("");
      setErrors({});
      create.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the modal opens
  }, [opened]);

  const canSubmit = name.trim() !== "" && slug !== "" && president.trim() !== "";
  const general = generalError(errors, ["name", "slug", "president_name"]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!canSubmit) return;
    setErrors({});
    create.mutate(
      { name: name.trim(), slug, president_name: president.trim() },
      {
        onSuccess: (created) => onCreated(created, created.president_name || president.trim()),
        onError: (error) => setErrors(formErrors(error, "Could not create the society.")),
      },
    );
  }

  return (
    <Modal opened={opened} onClose={onClose} title="New society" centered>
      <form onSubmit={submit}>
        <Stack>
          <TextInput
            label="Society name"
            maxLength={120}
            value={name}
            onChange={(e) => {
              setName(e.currentTarget.value);
              if (!slugEdited) setSlug(slugify(e.currentTarget.value));
            }}
            error={errors.name}
            required
            data-autofocus
          />
          <TextInput
            label="Short name for web addresses and usernames"
            description="Lower-case letters, numbers and dashes. It cannot be changed later."
            maxLength={50}
            value={slug}
            onChange={(e) => {
              setSlugEdited(true);
              setSlug(e.currentTarget.value);
            }}
            error={errors.slug}
            autoCapitalize="none"
            required
          />
          <TextInput
            label="President's full name"
            description="They get the first login and set up the rest of the society."
            maxLength={100}
            value={president}
            onChange={(e) => setPresident(e.currentTarget.value)}
            error={errors.president_name}
            required
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
            <Button type="submit" loading={create.isPending} disabled={!canSubmit}>
              Create society
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}
