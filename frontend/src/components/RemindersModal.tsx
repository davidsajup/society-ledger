import { Alert, Button, Group, List, Modal, Skeleton, Stack, Text } from "@mantine/core";
import { IconAlertTriangle, IconCircleCheck } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import { useReminderPreview, useSendReminders } from "../api/hooks";
import type { ReminderResult } from "../api/types";

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;

/**
 * Email every flat that owes money. The dialog shows what will happen first (counts only: the
 * office-bearer never sees an address) and then what did happen.
 */
export function RemindersModal({
  opened,
  societyId,
  onClose,
}: {
  opened: boolean;
  societyId: number;
  onClose: () => void;
}) {
  const preview = useReminderPreview(societyId, opened);
  const send = useSendReminders(societyId);
  const [result, setResult] = useState<ReminderResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (opened) {
      setResult(null);
      setError(null);
      send.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the dialog opens
  }, [opened]);

  function submit() {
    setError(null);
    send.mutate(undefined, {
      onSuccess: setResult,
      onError: (e) =>
        setError(
          e instanceof ApiError && e.status === 429
            ? "Reminders can be sent six times an hour. Please try again later."
            : e instanceof ApiError
              ? e.message
              : "Could not send the reminders.",
        ),
    });
  }

  const data = preview.data;
  const nothingToSend = data !== undefined && data.recipients === 0;

  return (
    <Modal opened={opened} onClose={onClose} title="Remind flats that owe" centered>
      {result ? (
        <Stack>
          <Group gap="sm" wrap="nowrap" align="flex-start">
            <IconCircleCheck size={22} aria-hidden style={{ flexShrink: 0 }} />
            <Text fw={700}>
              {result.sent === 0
                ? "No emails were sent."
                : `${plural(result.sent, "email was", "emails were")} sent to ${plural(
                    result.flats_reminded,
                    "flat",
                    "flats",
                  )}.`}
            </Text>
          </Group>
          <List size="sm" spacing={4}>
            {result.failed > 0 && (
              <List.Item>
                {plural(result.failed, "email", "emails")} could not be sent. Press the button
                again later to retry only those.
              </List.Item>
            )}
            {result.flats_deferred > 0 && (
              <List.Item>
                {plural(result.flats_deferred, "flat is", "flats are")} still to do. Press the
                button again to send the rest.
              </List.Item>
            )}
            {result.flats_without_email > 0 && (
              <List.Item>
                {plural(result.flats_without_email, "flat has", "flats have")} no email on file, so
                nothing could be sent there.
              </List.Item>
            )}
            {result.flats_cooling_down > 0 && (
              <List.Item>
                {plural(result.flats_cooling_down, "flat was", "flats were")} reminded in the last 7
                days and was skipped.
              </List.Item>
            )}
          </List>
          <Group justify="flex-end">
            <Button onClick={onClose}>Done</Button>
          </Group>
        </Stack>
      ) : (
        <Stack>
          <Text size="sm" c="dimmed">
            Each person on a flat that owes money gets an email with that flat&apos;s amount. A flat
            is reminded at most once every 7 days. You will not see anyone&apos;s email address.
          </Text>

          {preview.isPending && opened && (
            <Stack gap="xs">
              <Skeleton height={14} />
              <Skeleton height={14} width="70%" />
            </Stack>
          )}
          {preview.isError && (
            <Alert color="red" role="alert" icon={<IconAlertTriangle size={18} />}>
              Could not check who owes money. Please try again.
            </Alert>
          )}

          {data && (
            <List size="sm" spacing={4}>
              <List.Item>
                <b>{plural(data.flats_owing, "flat owes", "flats owe")}</b> money.
              </List.Item>
              <List.Item>
                <b>{plural(data.recipients, "email", "emails")}</b> will be sent, to{" "}
                {plural(data.flats_eligible, "flat", "flats")}.
              </List.Item>
              {data.flats_cooling_down > 0 && (
                <List.Item>
                  {plural(data.flats_cooling_down, "flat was", "flats were")} reminded in the last 7
                  days and will be skipped.
                </List.Item>
              )}
              {data.flats_without_email > 0 && (
                <List.Item>
                  {plural(data.flats_without_email, "flat has", "flats have")} no email on file and
                  cannot be reminded here.
                </List.Item>
              )}
              {data.recipients > data.batch_limit && (
                <List.Item>
                  One press sends at most {data.batch_limit} emails. Press again for the rest.
                </List.Item>
              )}
            </List>
          )}

          {nothingToSend && (
            <Text size="sm">There is nobody to email right now.</Text>
          )}
          {error && (
            <Alert color="red" role="alert" icon={<IconAlertTriangle size={18} />}>
              {error}
            </Alert>
          )}
          <Group justify="flex-end">
            <Button variant="default" onClick={onClose}>
              Cancel
            </Button>
            <Button
              loading={send.isPending}
              disabled={!data || nothingToSend}
              onClick={submit}
            >
              Send reminders
            </Button>
          </Group>
        </Stack>
      )}
    </Modal>
  );
}
