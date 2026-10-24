import { Alert, Button, Card, Divider, Stack, Text, ThemeIcon } from "@mantine/core";
import {
  IconBuildingEstate,
  IconClipboardList,
  IconCoin,
  IconCrown,
  IconHome,
  IconPlayerPlay,
} from "@tabler/icons-react";
import { useNavigate } from "react-router-dom";

import { useDemo, useDemoLogin } from "../api/hooks";
import type { DemoAccount, Role } from "../api/types";
import { homePath } from "../auth/session";

export const capitalise = (name: string) => name.charAt(0).toUpperCase() + name.slice(1);

const ROLE: Record<Role, { label: string; icon: typeof IconCoin; color: string }> = {
  president: { label: "President", icon: IconCrown, color: "violet" },
  secretary: { label: "Secretary", icon: IconClipboardList, color: "indigo" },
  treasurer: { label: "Treasurer", icon: IconCoin, color: "teal" },
  resident: { label: "Resident", icon: IconHome, color: "sunrise" },
};

function blurb(account: DemoAccount): string {
  // Office-bearers are also residents who pay their own dues, so they have a flat too.
  const flat = account.flat_label ? `Flat ${account.flat_label} · ` : "";
  switch (account.role) {
    case "president":
      return `${flat}oversees the books and manages people`;
    case "secretary":
      return `${flat}manages flats, people and logins`;
    case "treasurer":
      return `${flat}records payments and expenses`;
    case "resident":
      return `${flat}your dues, statement and receipts`;
  }
}

/** One-click demo logins. Renders nothing unless the server has demo mode switched on. */
export function DemoPicker() {
  const demo = useDemo();
  const login = useDemoLogin();
  const navigate = useNavigate();

  if (!demo.data?.enabled || demo.data.accounts.length === 0) return null;

  return (
    <Card padding="xl" shadow="sm" style={{ flex: "1 1 340px", maxWidth: 420 }}>
      <Stack gap="sm">
        <Stack gap={2}>
          <Text fw={800} size="lg">
            <IconPlayerPlay size={18} style={{ verticalAlign: "-3px" }} /> Just looking around?
          </Text>
          <Text size="sm" c="dimmed">
            Pick a role to explore a demo society ({demo.data.accounts[0].society_name}). No
            password needed, and everything here is fake data.
          </Text>
        </Stack>

        {login.isError && (
          <Alert color="red" role="alert">
            Could not start the demo. Please try again.
          </Alert>
        )}

        {demo.data.accounts.map((account) => {
          const look = ROLE[account.role];
          return (
            <Button
              key={account.username}
              variant="light"
              color={look.color}
              size="lg"
              h="auto"
              py="sm"
              justify="flex-start"
              fullWidth
              loading={login.isPending && login.variables === account.username}
              disabled={login.isPending}
              leftSection={
                <ThemeIcon variant="white" color={look.color} radius="xl" size="lg">
                  <look.icon size={18} />
                </ThemeIcon>
              }
              onClick={() =>
                login.mutate(account.username, {
                  // Demo logins may belong to other societies too; go straight into the one named above.
                  onSuccess: (me) => {
                    const demoSociety = demo.data.accounts[0].society_name;
                    const here = me.memberships.find((m) => m.society_name === demoSociety);
                    navigate(here ? homePath(here) : "/", { replace: true });
                  },
                })
              }
            >
              <div style={{ textAlign: "left", whiteSpace: "normal" }}>
                <Text fw={800} size="sm" inherit>
                  {capitalise(account.username)} · {look.label}
                </Text>
                <Text size="xs" c="dimmed" fw={500}>
                  {blurb(account)}
                </Text>
              </div>
            </Button>
          );
        })}
        <Divider />
        <Text size="xs" c="dimmed" ta="center">
          <IconBuildingEstate size={12} style={{ verticalAlign: "-1px" }} /> Dues, payments,
          receipts and an audit trail for housing societies.
        </Text>
      </Stack>
    </Card>
  );
}
