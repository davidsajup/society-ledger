import {
  Alert,
  Button,
  Card,
  FileInput,
  Group,
  List,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconDownload, IconUpload } from "@tabler/icons-react";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { useImportConfirm, useImportPreview } from "../../api/hooks";
import type { ImportPreview, ImportProblem, ImportResult } from "../../api/types";
import { useMembership } from "../../auth/session";
import { ConfirmModal } from "../../components/ConfirmModal";
import { CredentialSlips } from "../../components/CredentialSlips";
import { Money } from "../../components/common";
import { downloadCsv } from "../../lib/csv";
import { cycleWord } from "../../lib/dates";

const SHOWN_ROWS = 50;

/** What a problem looks like in plain words: "Row 3, name: Enter the person's name." */
const describeProblem = (p: ImportProblem) =>
  p.row > 0 ? `Row ${p.row}, ${p.field}: ${p.message}` : p.message;

/** The server's 400 for a file or for confirm, as a list of plain sentences. */
function problemsFrom(error: unknown): string[] {
  if (!(error instanceof ApiError)) return ["Something went wrong. Please try again."];
  const data = error.data as { errors?: ImportProblem[]; file?: string[] } | null;
  if (data?.errors?.length) return data.errors.map(describeProblem);
  if (data?.file?.length) return data.file;
  if (error.status === 429) return ["Too many uploads. Please wait a few minutes and try again."];
  return [error.message];
}

/**
 * Upload a CSV or Excel sheet, check it, then create every flat, person and login at once.
 * Nothing is created until the president confirms, and it is all-or-nothing.
 */
export function ImportPage() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const per = cycleWord(membership.billing_cycle_months);
  const preview = useImportPreview(societyId);
  const confirm = useImportConfirm(societyId);

  const [file, setFile] = useState<File | null>(null);
  const [checked, setChecked] = useState<ImportPreview | null>(null);
  const [problems, setProblems] = useState<string[]>([]);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [asking, setAsking] = useState(false);

  function reset() {
    setFile(null);
    setChecked(null);
    setProblems([]);
    setResult(null);
    preview.reset();
    confirm.reset();
  }

  function check() {
    if (!file) return;
    setProblems([]);
    preview.mutate(file, {
      onSuccess: setChecked,
      onError: (error) => setProblems(problemsFrom(error)),
    });
  }

  function create() {
    if (!checked) return;
    setProblems([]);
    confirm.mutate(checked.rows, {
      onSuccess: (done) => {
        setResult(done);
        setChecked(null);
        notifications.show({
          color: "teal",
          title: "Created",
          message: `${done.flats} flats and ${done.people} logins`,
        });
      },
      onError: (error) => setProblems(problemsFrom(error)),
    });
  }

  function template() {
    downloadCsv("flats-template.csv", [
      ["Flat", "Name", "Phone", "Email", "Maintenance"],
      ["A-101", "Ravi Kumar", "9876543210", "ravi@example.com", "4500"],
      ["A-102", "Meena Iyer", "", "meena@example.com", "4500"],
    ]);
  }

  // Step 3: the logins exist. This is the one chance to print them.
  if (result) {
    return (
      <>
        <CredentialSlips
          logins={result.logins}
          societyName={membership.society_name}
          onDone={() => setAsking(true)}
        />
        <ConfirmModal
          opened={asking}
          title="Leave without the passwords?"
          confirmLabel="Yes, I have saved them"
          loading={false}
          onConfirm={() => {
            setAsking(false);
            reset();
          }}
          onClose={() => setAsking(false)}
        >
          Once you leave this page the passwords cannot be shown again. Have you printed the slips
          or downloaded the file?
        </ConfirmModal>
      </>
    );
  }

  const hasErrors = (checked?.errors.length ?? 0) > 0;

  return (
    <Stack gap="lg">
      <Stack gap={4} className="no-print">
        <Title order={3}>Add flats and people from a file</Title>
        <Text size="sm" c="dimmed">
          Upload a CSV or Excel (.xlsx) sheet with one row per person. Nothing is created until you
          have checked the preview and confirmed.
        </Text>
      </Stack>

      {checked === null && (
        <Card padding="md">
          <Stack gap="md">
            <div>
              <Text fw={700}>What the sheet needs</Text>
              <List size="sm" spacing={4} mt={4}>
                <List.Item>
                  One heading row with <b>Flat</b>, <b>Name</b> and <b>Maintenance</b>. Phone and
                  Email are optional.
                </List.Item>
                <List.Item>
                  <b>Maintenance</b> is the amount for one {per}, for the whole flat. If two people
                  share a flat, give each their own row with the same flat and amount.
                </List.Item>
                <List.Item>
                  Flats that already exist are not changed: edit those on the Flats page.
                </List.Item>
              </List>
            </div>
            <Group>
              <Button
                variant="light"
                leftSection={<IconDownload size={18} />}
                onClick={template}
              >
                Download a template
              </Button>
            </Group>
            <FileInput
              label="Your file"
              placeholder="Choose a .csv or .xlsx file"
              accept=".csv,.xlsx"
              clearable
              value={file}
              onChange={(f) => {
                setFile(f);
                setProblems([]);
              }}
            />
            {problems.length > 0 && (
              <Alert color="red" icon={<IconAlertTriangle size={18} />} role="alert">
                {problems.map((p) => (
                  <Text key={p} size="sm">
                    {p}
                  </Text>
                ))}
              </Alert>
            )}
            <Group justify="flex-end">
              <Button
                leftSection={<IconUpload size={18} />}
                disabled={file === null}
                loading={preview.isPending}
                onClick={check}
              >
                Check the file
              </Button>
            </Group>
          </Stack>
        </Card>
      )}

      {checked !== null && (
        <Stack gap="md">
          <Card padding="md">
            <Text fw={800} fz="lg">
              {checked.summary.flats} {checked.summary.flats === 1 ? "flat" : "flats"} ·{" "}
              {checked.summary.people} {checked.summary.people === 1 ? "person" : "people"}
            </Text>
            <Text size="sm">
              <Money value={checked.summary.total_per_cycle} fw={700} inherit /> billed every {per}{" "}
              in total
            </Text>
          </Card>

          {checked.ignored_columns.length > 0 && (
            <Alert color="blue" title="Some columns were ignored">
              {checked.ignored_columns.join(", ")}
            </Alert>
          )}

          {hasErrors && (
            <Alert
              color="red"
              icon={<IconAlertTriangle size={18} />}
              title={`${checked.errors.length} ${checked.errors.length === 1 ? "problem" : "problems"} to fix in the file`}
              role="alert"
            >
              <Text size="sm" mb="xs">
                Nothing has been created. Fix these in your sheet and upload it again.
              </Text>
              <List size="sm" spacing={2}>
                {checked.errors.map((p) => (
                  <List.Item key={`${p.row}-${p.field}-${p.message}`}>{describeProblem(p)}</List.Item>
                ))}
              </List>
            </Alert>
          )}

          {problems.length > 0 && (
            <Alert color="red" icon={<IconAlertTriangle size={18} />} role="alert">
              {problems.map((p) => (
                <Text key={p} size="sm">
                  {p}
                </Text>
              ))}
            </Alert>
          )}

          {checked.rows.length > 0 && (
            <Card padding={0}>
              <ScrollArea>
                <Table verticalSpacing="xs" horizontalSpacing="md" miw={560}>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Row</Table.Th>
                      <Table.Th>Flat</Table.Th>
                      <Table.Th>Name</Table.Th>
                      <Table.Th>Phone</Table.Th>
                      <Table.Th>Email</Table.Th>
                      <Table.Th ta="right">Per {per}</Table.Th>
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {checked.rows.slice(0, SHOWN_ROWS).map((r) => (
                      <Table.Tr key={r.row}>
                        <Table.Td>{r.row}</Table.Td>
                        <Table.Td fw={700} style={{ whiteSpace: "nowrap" }}>
                          {r.flat}
                        </Table.Td>
                        <Table.Td>{r.name}</Table.Td>
                        <Table.Td>{r.phone || "—"}</Table.Td>
                        <Table.Td>{r.email || "—"}</Table.Td>
                        <Table.Td ta="right">
                          <Money value={r.maintenance} />
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </ScrollArea>
              {checked.rows.length > SHOWN_ROWS && (
                <Text size="sm" c="dimmed" p="sm">
                  Showing the first {SHOWN_ROWS} of {checked.rows.length} rows.
                </Text>
              )}
            </Card>
          )}

          <Group justify="space-between">
            <Button variant="default" onClick={reset}>
              Choose a different file
            </Button>
            <Button
              disabled={hasErrors || checked.rows.length === 0}
              loading={confirm.isPending}
              onClick={create}
            >
              Create {checked.summary.flats} {checked.summary.flats === 1 ? "flat" : "flats"} and{" "}
              {checked.summary.people} {checked.summary.people === 1 ? "login" : "logins"}
            </Button>
          </Group>
        </Stack>
      )}
    </Stack>
  );
}
