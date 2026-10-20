import { Alert, Button, Stack, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** When this changes (e.g. the user navigates elsewhere) a failed page gets another chance. */
  resetKey: string;
}

/**
 * If a page throws while rendering, React unmounts the whole app and the user sees a blank
 * screen. This catches that inside the page area, keeps the header and navigation usable, and
 * explains what happened.
 */
export class ErrorBoundary extends Component<Props, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidUpdate(previous: Props) {
    if (this.state.failed && previous.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  componentDidCatch(error: unknown) {
    console.error("A page failed to render:", error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <Alert color="red" icon={<IconAlertTriangle />} title="This page hit a problem" radius="lg">
        <Stack gap="sm" align="flex-start">
          <Text size="sm">
            Something unexpected went wrong while showing this page. Your data is safe. Try
            reloading, or use the menu to go somewhere else.
          </Text>
          <Button size="xs" variant="light" color="red" onClick={() => window.location.reload()}>
            Reload page
          </Button>
        </Stack>
      </Alert>
    );
  }
}
