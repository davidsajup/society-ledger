import { Button, Card, Center, Stack, Text, Title } from "@mantine/core";
import { Navigate, useNavigate } from "react-router-dom";

import { useLogout } from "../api/hooks";
import { homePath, useSession } from "../auth/session";

/** "/" sends you to your dashboard; with several societies you pick one first. */
export function HomeRedirect() {
  const { me } = useSession();
  const navigate = useNavigate();
  const logout = useLogout();

  // The super admin belongs to no society: their home is the onboarding page.
  if (me.is_platform_admin) return <Navigate to="/platform" replace />;

  if (me.memberships.length === 1) {
    return <Navigate to={homePath(me.memberships[0])} replace />;
  }

  return (
    <Center mih="100dvh" p="md">
      <Card maw={460} w="100%" padding="xl">
        <Stack gap="md">
          <Title order={2}>
            {me.memberships.length ? "Choose a society" : "No society yet"}
          </Title>
          {me.memberships.length === 0 && (
            <Text c="dimmed">
              Your account isn&apos;t part of any society. Ask your society admin to add you.
            </Text>
          )}
          {me.memberships.map((m) => (
            <Button
              key={m.society_id}
              variant="light"
              size="lg"
              justify="space-between"
              onClick={() => navigate(homePath(m))}
              rightSection={<Text size="sm" tt="capitalize">{m.role}</Text>}
            >
              {m.society_name}
            </Button>
          ))}
          <Button variant="subtle" color="gray" onClick={() => logout.mutate()}>
            Log out
          </Button>
        </Stack>
      </Card>
    </Center>
  );
}
