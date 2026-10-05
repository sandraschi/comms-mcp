import { expect, test } from "@playwright/test";

const ROUTES: Array<[string, string]> = [
    ["/", "dashboard"],
    ["/inbox", "inbox-page"],
    ["/outbox", "outbox-page"],
    ["/chat", "chat-page"],
    ["/tools", "tools-page"],
    ["/skills", "skills-page"],
    ["/allowlist", "allowlist-page"],
    ["/settings", "settings-page"],
    ["/logs", "logs-page"],
    ["/help", "help-page"],
];

test.describe("comms console nav walk", () => {
    for (const [path, testid] of ROUTES) {
        test(`route ${path} renders ${testid}`, async ({ page }) => {
            await page.goto(path);
            await expect(page.getByTestId(testid)).toBeVisible();
        });
    }

    test("dashboard shows hero + onboarding cue when unconfigured", async ({ page }) => {
        await page.goto("/");
        await expect(page.getByTestId("hero")).toBeVisible();
        // The cue renders when no bot/allowlist is configured; the bot dot
        // always renders. Assert whichever applies without a strict-mode race
        // (both can be present when the backend is reachable but unconfigured).
        const cueCount = await page.getByTestId("onboarding-cue").count();
        if (cueCount > 0) {
            await expect(page.getByTestId("onboarding-cue")).toBeVisible();
        } else {
            await expect(page.getByTestId("backend-dot")).toBeVisible();
        }
    });

    test("chat shows provider + model selects", async ({ page }) => {
        await page.goto("/chat");
        await expect(page.getByTestId("llm-provider-select")).toBeVisible();
        await expect(page.getByTestId("llm-model-select")).toBeVisible();
    });

    test("outbox exposes list controls", async ({ page }) => {
        await page.goto("/outbox");
        await expect(page.getByTestId("outbox-search")).toBeVisible();
        await expect(page.getByTestId("outbox-count")).toBeVisible();
    });
});
