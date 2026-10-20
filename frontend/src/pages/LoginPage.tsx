import {
  Alert,
  Button,
  Card,
  Center,
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
      <Card maw={420} w="100%" padding="xl" shadow="sm">
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
    </Center>
  );
}
