import { Alert, Button, Card, Group, SimpleGrid, Stack, Text, Title } from "@mantine/core";
import { IconDownload, IconPrinter, IconShieldLock } from "@tabler/icons-react";

import type { ImportedLogin } from "../api/types";
import { calendarDay } from "../lib/dates";
import { downloadCsv } from "../lib/csv";

/**
 * One slip per person with their username and temporary password, to print and hand out.
 * The passwords exist only in this page's memory: the server stored hashes and cannot show them
 * again, so printing or downloading here is the only chance.
 */
export function CredentialSlips({
  logins,
  societyName,
  onDone,
}: {
  logins: ImportedLogin[];
  societyName: string;
  onDone: () => void;
}) {
  function download() {
    downloadCsv("login-slips.csv", [
      ["Flat", "Name", "Role", "Username", "Temporary password", "Valid until"],
      ...logins.map((l) => [
        l.flat,
        l.name,
        l.role,
        l.username,
        l.temp_password,
        calendarDay(l.expires_at),
      ]),
    ]);
  }

  return (
    <Stack gap="lg">
      <Stack gap="md" className="no-print">
        <Title order={3}>
          {logins.length} {logins.length === 1 ? "login is" : "logins are"} ready
        </Title>
        <Alert color="yellow" icon={<IconShieldLock size={18} />} title="Shown only once">
          These passwords cannot be shown again. Print the slips or download the file now, and
          hand each one to its owner privately. Anyone who loses theirs can get a new one from the
          People page.
        </Alert>
        <Group>
          <Button leftSection={<IconPrinter size={18} />} onClick={() => window.print()}>
            Print slips
          </Button>
          <Button variant="light" leftSection={<IconDownload size={18} />} onClick={download}>
            Download as a file
          </Button>
          <Button variant="default" onClick={onDone}>
            I have saved them
          </Button>
        </Group>
      </Stack>

      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm" className="slips-grid">
        {logins.map((login) => (
          <Card key={login.username} className="slip" padding="md">
            <Text size="xs" c="dimmed">
              {societyName}
            </Text>
            <Text fw={800} fz="lg">
              Flat {login.flat} · {login.name}
            </Text>
            <Text size="sm" mt="xs">
              Username
            </Text>
            <Text ff="monospace" fw={700} style={{ wordBreak: "break-all" }}>
              {login.username}
            </Text>
            <Text size="sm" mt="xs">
              Temporary password
            </Text>
            <Text ff="monospace" fw={800} fz="lg">
              {login.temp_password}
            </Text>
            <Text size="xs" c="dimmed" mt="xs">
              Open {window.location.origin} and log in. You will be asked to choose your own
              password. This one stops working on {calendarDay(login.expires_at)}.
            </Text>
          </Card>
        ))}
      </SimpleGrid>
    </Stack>
  );
}
