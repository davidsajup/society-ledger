import { Alert, Button, Card, Center, PasswordInput, Stack, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconKey, IconShieldLock } from "@tabler/icons-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { formErrors, generalError } from "../api/client";
import { useChangePassword, useLogout } from "../api/hooks";
import { useSession } from "../auth/session";

/**
 * Used in two ways: forced (first login with a temporary password: no way out except logging
 * out) and voluntary (from the account menu). The server enforces the forced case on every API
 * call; this page is just where the person goes to fix it.
 */
export function ChangePasswordPage() {
  const { me } = useSession();
  const forced = me.must_change_password;
  const change = useChangePassword();
  const logout = useLogout();
  const navigate = useNavigate();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});

  const mismatch = confirm !== "" && next !== confirm;
  const general = generalError(errors, ["current_password", "new_password"]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (next !== confirm) return;
    setErrors({});
    change.mutate(
      { current_password: current, new_password: next },
      {
        onSuccess: () => {
          notifications.show({
            color: "teal",
            title: "Password changed",
            message: "You're all set.",
          });
          navigate("/", { replace: true });
        },
        onError: (error) => setErrors(formErrors(error, "Could not change the password.")),
      },
    );
  }

  return (
    <Center mih="100dvh" p="md">
      <Card maw={440} w="100%" padding="xl" shadow="sm">
        <form onSubmit={submit}>
          <Stack gap="md">
            <Stack gap={4} align="center">
              {forced ? (
                <IconShieldLock size={44} color="var(--mantine-color-sunrise-7)" stroke={1.6} />
              ) : (
                <IconKey size={44} color="var(--mantine-color-sunrise-7)" stroke={1.6} />
              )}
              <Title order={2} ta="center">
                {forced ? "Choose your own password" : "Change password"}
              </Title>
              {forced && (
                <Text c="dimmed" size="sm" ta="center">
                  Welcome, {me.username}. The password you were given is temporary. Replace it with
                  one only you know before you continue.
                </Text>
              )}
            </Stack>

            {general && (
              <Alert color="red" role="alert">
                {general}
              </Alert>
            )}

            <PasswordInput
              label={forced ? "Temporary password" : "Current password"}
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.currentTarget.value)}
              error={errors.current_password}
              required
              data-autofocus
            />
            <PasswordInput
              label="New password"
              description="At least 8 characters. Not a common password, and not all numbers."
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.currentTarget.value)}
              error={errors.new_password}
              required
            />
            <PasswordInput
              label="Repeat new password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.currentTarget.value)}
              error={mismatch ? "The two passwords do not match." : undefined}
              required
            />

            <Button type="submit" size="lg" loading={change.isPending} disabled={mismatch || !next}>
              {forced ? "Set my password" : "Change password"}
            </Button>
            {forced ? (
              <Button
                variant="subtle"
                color="gray"
                onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login") })}
              >
                Log out
              </Button>
            ) : (
              <Button variant="subtle" color="gray" onClick={() => navigate(-1)}>
                Cancel
              </Button>
            )}
          </Stack>
        </form>
      </Card>
    </Center>
  );
}
