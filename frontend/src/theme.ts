import { createTheme, type MantineColorsTuple } from "@mantine/core";

// "Friendly community app": warm terracotta/sunrise accent, rounded shapes, comfortable type.
// Shade 7 (#c9511c) is the filled-button colour in light mode: white text on it passes WCAG AA.
const sunrise: MantineColorsTuple = [
  "#fff4ee",
  "#ffe6d9",
  "#ffcab0",
  "#ffab84",
  "#ff8f5c",
  "#f77a3f",
  "#e8662a",
  "#c9511c",
  "#a84016",
  "#8a3312",
];

export const theme = createTheme({
  primaryColor: "sunrise",
  primaryShade: { light: 7, dark: 5 },
  colors: { sunrise },
  defaultRadius: "lg",
  fontFamily:
    '"Nunito", ui-rounded, "SF Pro Rounded", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
  headings: { fontWeight: "700" },
  fontSizes: { xs: "0.8125rem", sm: "0.9375rem", md: "1.0625rem", lg: "1.1875rem", xl: "1.375rem" },
  components: {
    Button: { defaultProps: { size: "md" } },
    TextInput: { defaultProps: { size: "md" } },
    PasswordInput: { defaultProps: { size: "md" } },
    Select: { defaultProps: { size: "md" } },
    Card: { defaultProps: { padding: "lg", withBorder: true } },
  },
});
