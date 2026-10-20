import { SegmentedControl, Stack } from "@mantine/core";
import { useState } from "react";

import { FlatsPage } from "./FlatsPage";
import { ResidentsPage } from "./ResidentsPage";

/** Residents and flats share one tab, which keeps the phone's bottom bar to five items. */
export function PeoplePage() {
  const [view, setView] = useState<"people" | "flats">("people");
  return (
    <Stack gap="lg">
      <SegmentedControl
        fullWidth
        value={view}
        onChange={(v) => setView(v as "people" | "flats")}
        data={[
          { value: "people", label: "People & roles" },
          { value: "flats", label: "Flats" },
        ]}
      />
      {view === "people" ? <ResidentsPage /> : <FlatsPage />}
    </Stack>
  );
}
