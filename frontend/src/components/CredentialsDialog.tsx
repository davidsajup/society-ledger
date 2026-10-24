import { Alert, Button, Code, CopyButton, Group, Modal, Stack, Text } from "@mantine/core";
import { IconCheck, IconCopy, IconShieldLock } from "@tabler/icons-react";

import type { IssuedLogin } from "../api/types";
import { calendarDay } from "../lib/dates";

/**
 * Shows a temporary password exactly once. The server cannot show it again, and neither can we.
 * `hint` is optional extra guidance for the person handing the login over.
 */
export function CredentialsDialog({
  issued,
  onDone,
  hint,
}: {
  issued: { login: IssuedLogin; person: string } | null;
  onDone: () => void;
  hint?: string;
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
          {hint && <Text size="sm">{hint}</Text>}

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
