import { SegmentedControl, Stack } from "@mantine/core";
import { useState } from "react";

import { BillingSettingsPanel } from "../../components/BillingSettingsPanel";
import { FlatsPage } from "./FlatsPage";
import { ImportPage } from "./ImportPage";
import { ResidentsPage } from "./ResidentsPage";

type View = "people" | "flats" | "import" | "billing";

/** Residents, flats and the bulk import share one tab, which keeps the phone's bar to five items. */
export function PeoplePage() {
  const [view, setView] = useState<View>("people");
  return (
    <Stack gap="lg">
      <SegmentedControl
        className="no-print"
        fullWidth
        value={view}
        onChange={(v) => setView(v as View)}
        data={[
          { value: "people", label: "People" },
          { value: "flats", label: "Flats" },
          { value: "import", label: "Import" },
          { value: "billing", label: "Billing" },
        ]}
      />
      {view === "people" && <ResidentsPage />}
      {view === "flats" && <FlatsPage />}
      {view === "billing" && <BillingSettingsPanel />}
      {/* Always mounted (just hidden): switching tabs must not throw away printed-once passwords. */}
      <div hidden={view !== "import"}>
        <ImportPage />
      </div>
    </Stack>
  );
}
