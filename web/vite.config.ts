import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Locally, proxy /api to the Functions host (func start -> :7071). On Static Web Apps /api is built in.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://localhost:7071" } },
});
