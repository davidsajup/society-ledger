import { Alert, Button, Card, Divider, Stack, Text, ThemeIcon } from "@mantine/core";
import {
  IconBuildingEstate,
  IconCoin,
  IconHome,
  IconPlayerPlay,
  IconShieldCheck,
} from "@tabler/icons-react";
import { useNavigate } from "react-router-dom";

import { useDemo, useDemoLogin } from "../api/hooks";
import type { DemoAccount, Role } from "../api/types";

export const capitalise = (name: string) => name.charAt(0).toUpperCase() + name.slice(1);

const ROLE: Record<Role, { label: string; icon: typeof IconCoin; color: string }> = {
  treasurer: { label: "Treasurer", icon: IconCoin, color: "teal" },
  admin: { label: "Admin", icon: IconShieldCheck, color: "violet" },
  resident: { label: "Resident", icon: IconHome, color: "sunrise" },
};

function blurb(account: DemoAccount): string {
  switch (account.role) {
    case "treasurer":
      return "Record payments and expenses, see who owes what";
    case "admin":
      return "Set up flats and residents, review the books";
    case "resident":
      return `Flat ${account.flat_label ?? ""} · your dues, statement and receipts`;
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
                login.mutate(account.username, { onSuccess: () => navigate("/", { replace: true }) })
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
