import { Stack } from "@mantine/core";

import { BillingSettingsPanel } from "../components/BillingSettingsPanel";

/** The billing schedule for every office-bearer (read-only for all but the president). */
export function BillingPage() {
  return (
    <Stack gap="lg">
      <BillingSettingsPanel />
    </Stack>
  );
}
