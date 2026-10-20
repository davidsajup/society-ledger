import {
  Alert,
  Button,
  Card,
  Center,
  Group,
  PasswordInput,
  Stack,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { IconBuildingEstate } from "@tabler/icons-react";
import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { DemoPicker } from "../components/DemoPicker";
import { useLogin, useMe } from "../api/hooks";

export function LoginPage() {
  const { data: me } = useMe();
  const login = useLogin();
  const navigate = useNavigate();
  const location = useLocation();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  if (me) return <Navigate to="/" replace />;

  function submit(event: FormEvent) {
    event.preventDefault();
    login.mutate(
      { username: username.trim(), password },
      { onSuccess: () => navigate((location.state as { from?: string } | null)?.from ?? "/", { replace: true }) },
    );
  }

  const error =
    login.error instanceof ApiError && login.error.status === 429
      ? "Too many attempts. Please wait a minute and try again."
      : login.error
        ? "Wrong username or password."
        : null;

  return (
    <Center mih="100dvh" p="md">
      {/* Demo card first (left on wide screens, on top on phones) so visitors see it at once.
          Both cards share one row when there is room and wrap when there is not. */}
      <Group align="flex-start" justify="center" gap="md" w="100%" maw={920} py="md">
      <DemoPicker />
      <Card padding="xl" shadow="sm" style={{ flex: "1 1 340px", maxWidth: 420 }}>
        <form onSubmit={submit}>
          <Stack gap="md">
            <Stack gap={4} align="center">
              <IconBuildingEstate size={44} color="var(--mantine-color-sunrise-7)" stroke={1.6} />
              <Title order={2}>Society Ledger</Title>
              <Text c="dimmed" size="sm" ta="center">
                Dues, payments and expenses for your housing society.
              </Text>
            </Stack>

            {error && (
              <Alert color="red" role="alert">
                {error}
              </Alert>
            )}

            <TextInput
              label="Username"
              autoComplete="username"
              autoCapitalize="none"
              value={username}
              onChange={(e) => setUsername(e.currentTarget.value)}
              required
              data-autofocus
            />
            <PasswordInput
              label="Password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.currentTarget.value)}
              required
            />
            <Button type="submit" size="lg" loading={login.isPending} fullWidth>
              Log in
            </Button>
          </Stack>
        </form>
      </Card>
      </Group>
    </Center>
  );
}
