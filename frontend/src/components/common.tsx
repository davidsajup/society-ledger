import {
  Alert,
  Button,
  Card,
  Center,
  Group,
  Loader,
  Skeleton,
  Stack,
  Text,
  type TextProps,
} from "@mantine/core";
import { IconAlertCircle, IconInbox } from "@tabler/icons-react";
import type { ReactNode } from "react";

import { ApiError } from "../api/client";
import { formatInr } from "../lib/money";

export function Money({ value, ...props }: { value: string } & TextProps) {
  return (
    <Text component="span" className="money" {...props}>
      {formatInr(value)}
    </Text>
  );
}

export function StatCard({
  label,
  value,
  hint,
  color,
}: {
  label: string;
  value: string;
  hint?: string;
  color?: string;
}) {
  return (
    <Card>
      <Text size="sm" c="dimmed" fw={600}>
        {label}
      </Text>
      <Text className="money" fz={{ base: 22, sm: 28 }} fw={800} c={color} mt={4}>
        {formatInr(value, true)}
      </Text>
      {hint && (
        <Text size="xs" c="dimmed" mt={2}>
          {hint}
        </Text>
      )}
    </Card>
  );
}

export function PageLoader() {
  return (
    <Center py="xl">
      <Loader color="sunrise" />
    </Center>
  );
}

export function CardSkeleton({ rows = 3 }: { rows?: number }) {
  return (
    <Stack gap="sm">
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} height={72} radius="lg" />
      ))}
    </Stack>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <Alert color="red" icon={<IconAlertCircle />} title="We could not load this" radius="lg">
      <Group justify="space-between" wrap="nowrap">
        <Text size="sm">
          {error instanceof ApiError ? error.message : "Check your internet connection, then try again."}
        </Text>
        {onRetry && (
          <Button variant="light" color="red" onClick={onRetry}>
            Try again
          </Button>
        )}
      </Group>
    </Alert>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card>
      <Stack align="center" gap={4} py="md">
        <IconInbox size={32} stroke={1.5} color="var(--mantine-color-dimmed)" />
        <Text fw={700}>{title}</Text>
        {children && (
          <Text size="sm" c="dimmed" ta="center">
            {children}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

const dateFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}
