import { SegmentedControl, Stack } from "@mantine/core";
import { useState } from "react";

import { FlatsPage } from "./FlatsPage";
import { ImportPage } from "./ImportPage";
import { ResidentsPage } from "./ResidentsPage";

type View = "people" | "flats" | "import";

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
        ]}
      />
      {view === "people" && <ResidentsPage />}
      {view === "flats" && <FlatsPage />}
      {/* Always mounted (just hidden): switching tabs must not throw away printed-once passwords. */}
      <div hidden={view !== "import"}>
        <ImportPage />
      </div>
    </Stack>
  );
}
