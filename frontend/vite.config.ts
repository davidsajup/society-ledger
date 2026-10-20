import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the browser talks only to Vite (http://localhost:5173). Vite forwards /api to
// Django, so the session cookie and CSRF token are same-origin: no CORS setup, no cross-site
// cookie problems. (Deployment is a separate decision; see docs/decisions.md.)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://127.0.0.1:8000" },
    },
  },
});
