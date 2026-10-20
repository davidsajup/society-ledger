import { Button, Group, Modal, Text } from "@mantine/core";
import type { ReactNode } from "react";

/** A confirmation step for actions that are hard to undo (here: reversals). */
export function ConfirmModal({
  opened,
  title,
  children,
  confirmLabel,
  loading,
  error,
  onConfirm,
  onClose,
}: {
  opened: boolean;
  title: string;
  children: ReactNode;
  confirmLabel: string;
  loading: boolean;
  error?: string | null;
  onConfirm: () => void;
  onClose: () => void;
}) {
  return (
    <Modal opened={opened} onClose={onClose} title={title} centered>
      <Text size="sm">{children}</Text>
      {error && (
        <Text size="sm" c="red.7" mt="sm" role="alert">
          {error}
        </Text>
      )}
      <Group justify="flex-end" mt="lg">
        <Button variant="default" onClick={onClose}>
          Keep it
        </Button>
        <Button color="red" loading={loading} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </Group>
    </Modal>
  );
}
