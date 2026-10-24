import { Badge } from "@mantine/core";

import type { ClaimMethod, ClaimStatus } from "../api/types";

export const METHOD_LABEL: Record<ClaimMethod, string> = {
  upi: "UPI",
  bank: "Bank transfer",
  cash: "Cash",
  cheque: "Cheque",
  other: "Other",
};

export const METHOD_OPTIONS = (Object.keys(METHOD_LABEL) as ClaimMethod[]).map((value) => ({
  value,
  label: METHOD_LABEL[value],
}));

/** Plain words for each state: the colour never carries the meaning on its own. */
const STATUS: Record<ClaimStatus, { label: string; color: string }> = {
  pending: { label: "Waiting for the treasurer", color: "yellow" },
  accepted: { label: "Recorded", color: "teal" },
  rejected: { label: "Not accepted", color: "red" },
  withdrawn: { label: "Withdrawn", color: "gray" },
};

export function ClaimStatusBadge({ status }: { status: ClaimStatus }) {
  const look = STATUS[status];
  return (
    <Badge variant="light" color={look.color}>
      {look.label}
    </Badge>
  );
}

/** Today as YYYY-MM-DD in the user's own timezone (what a date input expects). */
export const todayIso = () => new Date().toLocaleDateString("en-CA");
