import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Select,
  SegmentedControl,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconLock } from "@tabler/icons-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { formErrors, generalError } from "../api/client";
import { useBillingSettings, useSaveBillingSettings } from "../api/hooks";
import { useMembership } from "../auth/session";
import { can } from "../lib/capabilities";
import { calendarDay, cycleWord, upcomingCycleStarts } from "../lib/dates";
import { CardSkeleton, ErrorState } from "./common";

const cycleName = (months: number) => (months === 3 ? "every 3 months" : "every month");

/** Can billing start on `iso` for this cycle? Any month for monthly; Jan/Apr/Jul/Oct for quarterly. */
const isCycleStart = (iso: string, cycleMonths: number) =>
  iso.endsWith("-01") && (Number(iso.slice(5, 7)) - 1) % cycleMonths === 0;

/**
 * How the society is billed and when billing starts. Everyone in office can read it; only the
 * president can change it, and only until the first billing run exists (the server enforces both).
 */
export function BillingSettingsPanel() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const canChange = can(membership.role, "manageBilling");
  const settings = useBillingSettings(societyId);
  const save = useSaveBillingSettings(societyId);

  const [cycle, setCycle] = useState<"1" | "3">("3");
  const [start, setStart] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Fill the form from the server's answer, and again whenever a save changes it.
  useEffect(() => {
    if (!settings.data) return;
    setCycle(settings.data.billing_cycle_months === 1 ? "1" : "3");
    setStart(settings.data.billing_start ?? "");
    setReviewed(false);
  }, [settings.data]);

  const saved = settings.data;
  const startOptions = useMemo(() => {
    const dates = upcomingCycleStarts(Number(cycle));
    // Keep the saved date selectable while it fits the chosen cycle, so it never vanishes.
    const kept = saved?.billing_start;
    if (kept && isCycleStart(kept, Number(cycle)) && !dates.includes(kept)) {
      dates.push(kept);
      dates.sort();
    }
    return dates.map((d) => ({ value: d, label: calendarDay(d) }));
  }, [cycle, saved]);

  if (settings.isPending) return <CardSkeleton rows={4} />;
  if (settings.isError) return <ErrorState error={settings.error} onRetry={() => settings.refetch()} />;

  const current = settings.data;
  const cycleChanged = Number(cycle) !== current.billing_cycle_months;
  const needsReview = cycleChanged && current.flats_with_amounts > 0;
  const dirty = cycleChanged || start !== current.billing_start;
  const general = generalError(errors, ["billing_cycle_months", "billing_start", "amounts_reviewed"]);
  const editable = canChange && !current.locked;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!dirty || (needsReview && !reviewed)) return;
    setErrors({});
    save.mutate(
      { billing_cycle_months: Number(cycle), billing_start: start, amounts_reviewed: reviewed },
      {
        onSuccess: () =>
          notifications.show({ color: "teal", title: "Saved", message: "Billing schedule updated" }),
        onError: (error) => setErrors(formErrors(error, "Could not save the billing schedule.")),
      },
    );
  }

  return (
    <Stack gap="md">
      <Card>
        <Title order={3}>How billing works</Title>
        <Text size="sm" mt={4}>
          Billing adds one maintenance charge to every flat at the start of each{" "}
          {cycleWord(current.billing_cycle_months)}. The amount is the one set on the Flats page. It
          does not take any money: payments are recorded separately when residents pay, in as many
          installments as they like.
        </Text>
        <Text size="sm" c="dimmed" mt="xs">
          The charges are added automatically once the first billing date arrives. Nothing is
          charged before that date.
        </Text>
      </Card>

      <Card>
        <Group justify="space-between" align="flex-start" wrap="wrap" mb="sm">
          <Title order={4}>Billing schedule</Title>
          {current.locked ? (
            <Badge color="gray" leftSection={<IconLock size={12} />}>
              Billing has started
            </Badge>
          ) : (
            <Badge color="teal" variant="light">
              Not started yet
            </Badge>
          )}
        </Group>

        {!editable ? (
          <Stack gap={4}>
            <Text>
              Billed <b>{cycleName(current.billing_cycle_months)}</b>
            </Text>
            <Text>
              {current.locked ? "First billing date: " : "Billing starts on: "}
              <b>{current.billing_start ? calendarDay(current.billing_start) : "not set"}</b>
            </Text>
            <Text size="sm" c="dimmed" mt="xs">
              {current.locked
                ? "Billing has started, so the schedule is fixed. Charges are never edited or deleted."
                : "Only the president can change this."}
            </Text>
          </Stack>
        ) : (
          <form onSubmit={submit}>
            <Stack>
              <div>
                <Text size="sm" fw={500} mb={4}>
                  Maintenance is billed
                </Text>
                <SegmentedControl
                  fullWidth
                  value={cycle}
                  onChange={(v) => {
                    const next = v as "1" | "3";
                    setCycle(next);
                    setReviewed(false);
                    // The saved date stays if it fits the new cycle; otherwise the first valid one.
                    const kept = current.billing_start;
                    setStart(
                      kept && isCycleStart(kept, Number(next)) ? kept : upcomingCycleStarts(Number(next))[0],
                    );
                  }}
                  data={[
                    { value: "3", label: "Every 3 months" },
                    { value: "1", label: "Every month" },
                  ]}
                />
              </div>
              <Select
                label="Billing starts on"
                description={`The first day of a ${cycleWord(Number(cycle))}. Nothing is charged before this date.`}
                data={startOptions}
                value={start}
                onChange={(v) => v && setStart(v)}
                allowDeselect={false}
                error={errors.billing_start}
              />
              {needsReview && (
                <Alert color="yellow" icon={<IconAlertTriangle size={18} />} title="Check every flat's amount">
                  <Text size="sm">
                    Each flat&apos;s amount is for <b>one {cycleWord(Number(cycle))}</b>. The same
                    number now means a different total over the year, so the amounts on the Flats
                    page need updating.
                  </Text>
                  <Checkbox
                    mt="sm"
                    label="I have checked every flat's amount for the new schedule"
                    checked={reviewed}
                    onChange={(e) => setReviewed(e.currentTarget.checked)}
                    error={errors.amounts_reviewed}
                  />
                </Alert>
              )}
              {general && (
                <Alert color="red" role="alert">
                  {general}
                </Alert>
              )}
              <Text size="sm" c="dimmed">
                You can change this until the first billing date. After that it is fixed, because
                the charges are recorded permanently.
              </Text>
              <Group justify="flex-end">
                <Button
                  type="submit"
                  loading={save.isPending}
                  disabled={!dirty || (needsReview && !reviewed)}
                >
                  Save schedule
                </Button>
              </Group>
            </Stack>
          </form>
        )}
      </Card>
    </Stack>
  );
}
