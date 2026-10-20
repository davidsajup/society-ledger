import { Button, Group, Paper, Text } from "@mantine/core";
import { IconFlask } from "@tabler/icons-react";
import { useNavigate } from "react-router-dom";

import { useDemo, useLogout } from "../api/hooks";
import type { Role } from "../api/types";
import { useMembership, useSession } from "../auth/session";
import { capitalise } from "./DemoPicker";

const TRY: Record<Role, string> = {
  treasurer:
    "Record a payment for another flat. Your own flat's payments are recorded by someone else, by design.",
  president: "Open People to create a login or change a role, or record the treasurer's payment.",
  secretary: "Open People to create a login or change a role, or record the treasurer's payment.",
  resident: "Open Statement and tap a receipt to see it printed.",
};

/** A slim strip shown only to people who came in through the demo picker. */
export function DemoBanner() {
  const demo = useDemo();
  const { me } = useSession();
  const membership = useMembership();
  const logout = useLogout();
  const navigate = useNavigate();

  const isDemoUser = demo.data?.enabled && demo.data.accounts.some((a) => a.username === me.username);
  if (!isDemoUser) return null;

  return (
    <Paper
      className="no-print"
      radius={0}
      px="md"
      py={6}
      bg="var(--mantine-color-yellow-light)"
      style={{ borderBottom: "1px solid var(--mantine-color-yellow-light-hover)" }}
    >
      <Group justify="space-between" wrap="nowrap" gap="sm">
        <Group gap={8} wrap="nowrap" miw={0}>
          <IconFlask size={16} style={{ flexShrink: 0 }} />
          <Text size="xs" lh={1.3}>
            <b>Demo · fake data.</b> You are {capitalise(me.username)} ({membership.role}).{" "}
            <span style={{ opacity: 0.85 }}>Try: {TRY[membership.role]}</span>
          </Text>
        </Group>
        <Button
          size="compact-xs"
          variant="white"
          color="dark"
          onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login") })}
          style={{ flexShrink: 0 }}
        >
          Switch role
        </Button>
      </Group>
    </Paper>
  );
}
