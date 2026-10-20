import {
  ActionIcon,
  Avatar,
  Box,
  Container,
  Group,
  Menu,
  Paper,
  Text,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import {
  IconBuildingEstate,
  IconCalendarDollar,
  IconCash,
  IconChartPie,
  IconHistory,
  IconHome,
  IconKey,
  IconLogout,
  IconMoon,
  IconNotebook,
  IconReceipt2,
  IconSun,
  IconSwitchHorizontal,
  IconUsers,
} from "@tabler/icons-react";
import type { ComponentType } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useLogout } from "../api/hooks";
import type { Role } from "../api/types";
import { useMembership, useSession } from "../auth/session";
import { DemoBanner } from "../components/DemoBanner";
import { ErrorBoundary } from "../components/ErrorBoundary";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ size?: number; stroke?: number }>;
}

// At most 5 items so the phone's bottom bar stays usable. The admin reaches Expenses from the
// "Spent" card on Overview rather than from the bar.
function navFor(role: Role): NavItem[] {
  switch (role) {
    case "resident":
      return [
        { to: "home", label: "My home", icon: IconHome },
        { to: "statement", label: "Statement", icon: IconNotebook },
      ];
    case "treasurer":
      return [
        { to: "overview", label: "Overview", icon: IconChartPie },
        { to: "dues", label: "Dues", icon: IconCalendarDollar },
        { to: "payments", label: "Payments", icon: IconCash },
        { to: "expenses", label: "Expenses", icon: IconReceipt2 },
        { to: "activity", label: "Activity", icon: IconHistory },
      ];
    case "admin":
      return [
        { to: "overview", label: "Overview", icon: IconChartPie },
        { to: "dues", label: "Dues", icon: IconCalendarDollar },
        { to: "flats", label: "Flats", icon: IconBuildingEstate },
        { to: "residents", label: "Residents", icon: IconUsers },
        { to: "activity", label: "Activity", icon: IconHistory },
      ];
  }
}

export function AppLayout() {
  const { me } = useSession();
  const membership = useMembership();
  const navigate = useNavigate();
  const location = useLocation();
  const logout = useLogout();
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("light");
  const items = navFor(membership.role);
  const prefix = `/s/${membership.society_id}`;

  return (
    <Box mih="100dvh">
      <Paper component="header" radius={0} withBorder px="md" py="sm" pos="sticky" top={0} style={{ zIndex: 90 }}>
        <Container size="md" p={0}>
          <Group justify="space-between" wrap="nowrap">
            <Group gap="xs" wrap="nowrap" miw={0}>
              <IconBuildingEstate color="var(--mantine-color-sunrise-7)" />
              <div style={{ minWidth: 0 }}>
                <Text fw={800} lh={1.1} truncate>
                  {membership.society_name}
                </Text>
                <Text size="xs" c="dimmed" tt="capitalize">
                  {membership.role}
                  {membership.flat_label ? ` · Flat ${membership.flat_label}` : ""}
                </Text>
              </div>
            </Group>

            <Group gap="xs" wrap="nowrap">
              <Group gap={4} visibleFrom="sm">
                {items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={`${prefix}/${to}`}
                    style={{ textDecoration: "none" }}
                  >
                    {({ isActive }) => (
                      <Group
                        gap={6}
                        px="sm"
                        py={6}
                        style={{
                          borderRadius: "var(--mantine-radius-xl)",
                          background: isActive ? "var(--mantine-color-sunrise-light)" : undefined,
                          color: isActive
                            ? "var(--mantine-color-sunrise-light-color)"
                            : "var(--mantine-color-text)",
                        }}
                      >
                        <Icon size={18} />
                        <Text size="sm" fw={600} inherit>
                          {label}
                        </Text>
                      </Group>
                    )}
                  </NavLink>
                ))}
              </Group>

              <ActionIcon
                variant="subtle"
                color="gray"
                size="lg"
                aria-label="Toggle dark mode"
                onClick={() => setColorScheme(scheme === "dark" ? "light" : "dark")}
              >
                {scheme === "dark" ? <IconSun size={20} /> : <IconMoon size={20} />}
              </ActionIcon>

              <Menu position="bottom-end" width={220}>
                <Menu.Target>
                  <UnstyledButton aria-label="Account menu">
                    <Avatar color="sunrise" radius="xl" size="md">
                      {me.username.slice(0, 1).toUpperCase()}
                    </Avatar>
                  </UnstyledButton>
                </Menu.Target>
                <Menu.Dropdown>
                  <Menu.Label>Signed in as {me.username}</Menu.Label>
                  {me.memberships.length > 1 && (
                    <Menu.Item
                      leftSection={<IconSwitchHorizontal size={16} />}
                      onClick={() => navigate("/")}
                    >
                      Switch society
                    </Menu.Item>
                  )}
                  <Menu.Item
                    leftSection={<IconKey size={16} />}
                    onClick={() => navigate("/change-password")}
                  >
                    Change password
                  </Menu.Item>
                  <Menu.Item
                    color="red"
                    leftSection={<IconLogout size={16} />}
                    onClick={() => logout.mutate(undefined, { onSuccess: () => navigate("/login") })}
                  >
                    Log out
                  </Menu.Item>
                </Menu.Dropdown>
              </Menu>
            </Group>
          </Group>
        </Container>
      </Paper>

      <DemoBanner />

      <Container size="md" py="lg" className="page">
        <ErrorBoundary resetKey={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </Container>

      {items.length > 1 && (
        <Paper className="bottom-nav" hiddenFrom="sm" radius={0} withBorder component="nav">
          <Group grow gap={0} wrap="nowrap">
            {items.map(({ to, label, icon: Icon }) => (
              <NavLink key={to} to={`${prefix}/${to}`}>
                {({ isActive }) => (
                  <Box
                    py={8}
                    ta="center"
                    c={isActive ? "sunrise.7" : "dimmed"}
                    style={{ fontWeight: isActive ? 800 : 600 }}
                  >
                    <Icon size={22} stroke={isActive ? 2.2 : 1.7} />
                    <Text size="xs" inherit fz={11}>
                      {label}
                    </Text>
                  </Box>
                )}
              </NavLink>
            ))}
          </Group>
        </Paper>
      )}
    </Box>
  );
}

