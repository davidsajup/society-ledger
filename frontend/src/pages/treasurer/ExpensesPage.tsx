import { Badge, Button, Card, Group, Stack, Text, Title } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconArrowBackUp, IconPlus } from "@tabler/icons-react";
import { useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import { useExpenses, useReverseExpense } from "../../api/hooks";
import type { Expense } from "../../api/types";
import { useMembership } from "../../auth/session";
import { can } from "../../lib/capabilities";
import { CardSkeleton, EmptyState, ErrorState, Money, StatCard } from "../../components/common";
import { CATEGORIES, ExpenseModal } from "../../components/ExpenseModal";
import { ConfirmModal } from "../../components/ConfirmModal";

const label = (category: string) => CATEGORIES.find((c) => c.value === category)?.label ?? category;

const dayFormat = new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" });
// paid_on is a calendar date ("2026-10-05"), not a moment: parse it as local, never via UTC.
const formatDay = (iso: string) => dayFormat.format(new Date(`${iso}T00:00:00`));

export function ExpensesPage() {
  const membership = useMembership();
  const societyId = membership.society_id;
  const canWrite = can(membership.role, "recordExpense");
  const expenses = useExpenses(societyId);
  const reverse = useReverseExpense(societyId);
  const [adding, setAdding] = useState(false);
  const [target, setTarget] = useState<Expense | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The API does not flag reversed expenses; a row is reversed if another row points at it.
  const reversedIds = useMemo(
    () => new Set((expenses.data?.expenses ?? []).map((e) => e.reverses).filter((id) => id !== null)),
    [expenses.data],
  );

  if (expenses.isPending) return <CardSkeleton rows={5} />;
  if (expenses.isError) return <ErrorState error={expenses.error} onRetry={() => expenses.refetch()} />;

  function confirm() {
    if (!target) return;
    setError(null);
    reverse.mutate(target.id, {
      onSuccess: () => {
        notifications.show({ color: "teal", title: "Expense reversed", message: target.description });
        setTarget(null);
      },
      onError: (e) => setError(e instanceof ApiError ? e.message : "Could not reverse the expense."),
    });
  }

  return (
    <Stack gap="lg">
      <Group justify="space-between" align="flex-end" wrap="nowrap">
        <div style={{ flex: 1 }}>
          <StatCard label="Total spent" value={expenses.data.total_spent} />
        </div>
        {canWrite && (
          <Button size="lg" leftSection={<IconPlus size={18} />} onClick={() => setAdding(true)}>
            Add
          </Button>
        )}
      </Group>

      <Stack gap="xs">
        <Title order={3}>Expenses</Title>
        {expenses.data.expenses.length === 0 ? (
          <EmptyState title="No expenses yet">
            {canWrite ? "Use Add to record the first one." : "The treasurer records expenses here."}
          </EmptyState>
        ) : (
          expenses.data.expenses.map((expense) => {
            const reversed = reversedIds.has(expense.id);
            const isReversal = expense.reverses !== null;
            return (
              <Card key={expense.id} padding="md">
                <Group justify="space-between" wrap="nowrap" align="flex-start">
                  <div style={{ minWidth: 0 }}>
                    <Text fw={700}>{expense.description}</Text>
                    <Group gap={6} mt={2}>
                      <Badge variant="light" size="sm">
                        {label(expense.category)}
                      </Badge>
                      {reversed && (
                        <Badge variant="light" color="orange" size="sm">
                          Reversed
                        </Badge>
                      )}
                      {isReversal && (
                        <Badge variant="light" color="gray" size="sm">
                          Reversal
                        </Badge>
                      )}
                      <Text size="xs" c="dimmed">
                        {formatDay(expense.paid_on)} · {expense.created_by}
                      </Text>
                    </Group>
                  </div>
                  <Stack gap={4} align="flex-end">
                    <Text fw={800} className="money" td={reversed ? "line-through" : undefined} c={reversed ? "dimmed" : undefined}>
                      {isReversal ? "−" : ""}
                      <Money value={expense.amount} />
                    </Text>
                    {canWrite && !reversed && !isReversal && (
                      <Button
                        size="compact-xs"
                        variant="subtle"
                        color="red"
                        leftSection={<IconArrowBackUp size={14} />}
                        onClick={() => {
                          setError(null);
                          setTarget(expense);
                        }}
                      >
                        Reverse
                      </Button>
                    )}
                  </Stack>
                </Group>
              </Card>
            );
          })
        )}
      </Stack>

      <ExpenseModal societyId={societyId} opened={adding} onClose={() => setAdding(false)} />
      <ConfirmModal
        opened={target !== null}
        title="Reverse this expense?"
        confirmLabel="Reverse expense"
        loading={reverse.isPending}
        error={error}
        onConfirm={confirm}
        onClose={() => setTarget(null)}
      >
        {target && (
          <>
            This cancels <Money value={target.amount} fw={700} /> for &ldquo;{target.description}&rdquo; in the
            total. The original stays in the list, marked as reversed.
          </>
        )}
      </ConfirmModal>
    </Stack>
  );
}
