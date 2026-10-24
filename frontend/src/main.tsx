import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "./styles.css";

import { MantineProvider, type CSSVariablesResolver } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { ApiError } from "./api/client";
import { App } from "./App";
import { theme } from "./theme";

// Text colours that stay readable (4.5:1 or better) on white, on the tinted cards and on dark.
// Mantine's defaults (grey 6, teal 7, sunrise 7) measure 3.1 to 4.5 on white.
const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {
    "--mantine-color-dimmed": "#566069",
    "--mantine-color-teal-light-color": "#066649",
    "--mantine-color-sunrise-light-color": "#8a3312",
    "--text-positive": "#087f5b",
    "--text-owing": "#a84016",
  },
  dark: {
    "--mantine-color-dimmed": "#b8bcc2",
    "--text-positive": "#38d9a9",
    "--text-owing": "#ff9b6b",
  },
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      refetchOnWindowFocus: true,
      // Don't hammer the API on errors the user must fix (403/404 won't fix themselves).
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MantineProvider theme={theme} cssVariablesResolver={cssVariablesResolver} defaultColorScheme="auto">
      <Notifications position="top-center" />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </QueryClientProvider>
    </MantineProvider>
  </StrictMode>,
);
