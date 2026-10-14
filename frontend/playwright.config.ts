import { defineConfig } from "@playwright/test";

/**
 * Smoke test against a running stack: the backend (seeded scenario1) on BACKEND_URL and
 * `next dev` started here, proxying /api to it. See e2e/README.md.
 */
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  use: { baseURL: "http://localhost:3100" },
  webServer: {
    command: "pnpm dev --port 3100",
    url: "http://localhost:3100/login",
    reuseExistingServer: true,
    timeout: 120_000,
  },
});
