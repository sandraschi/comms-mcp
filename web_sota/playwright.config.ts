import { defineConfig, devices } from "@playwright/test";

/**
 * CUA webapp smoke harness (VERIFICATION_STANDARDS / cua_webapp_testing).
 * Boots the Vite dev server (which proxies /api to the backend on :11205) and
 * walks every console route asserting the page's data-testid anchor.
 */
export default defineConfig({
    testDir: "./e2e",
    timeout: 30_000,
    expect: { timeout: 10_000 },
    fullyParallel: false,
    reporter: [["list"]],
    use: {
        baseURL: "http://127.0.0.1:11204",
        trace: "on-first-retry",
    },
    webServer: {
        command: "bun run dev -- --port 11204 --host 127.0.0.1",
        url: "http://127.0.0.1:11204",
        reuseExistingServer: true,
        timeout: 120_000,
    },
    projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
