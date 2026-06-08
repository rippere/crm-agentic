import { test, expect } from "@playwright/test";

// Focused coverage for the roadmap-batch frontend lane:
//   • Honest marketing — the landing page must not advertise compliance /
//     uptime claims we can't substantiate.
//   • Resilient list loads — inbox + tasks render their content in demo mode
//     (the success path of the refactored loadMessages / loadTasks) and do not
//     fall into the error/retry banner state.
//
// All tests run in demo mode (NEXT_PUBLIC_DEMO_MODE=true), matching smoke.spec.ts.

test.describe("Honest marketing claims", () => {
  test("landing page drops unsubstantiated compliance / uptime claims", async ({ page }) => {
    await page.goto("/");

    // The page must render (hero CTA present).
    await expect(page.getByRole("link", { name: /launch app/i }).first()).toBeVisible({ timeout: 10_000 });

    const body = page.locator("body");
    // None of the removed false claims should appear anywhere on the page.
    await expect(body).not.toContainText("SOC 2");
    await expect(body).not.toContainText("99.9% uptime");
    await expect(body).not.toContainText("99.9% Uptime");
    await expect(body).not.toContainText("99.99% SLA");
    await expect(body).not.toContainText("GDPR Compliant");

    // Honest replacements are present.
    await expect(body).toContainText("No credit card required");
    await expect(body).toContainText(/you own your data/i);
  });
});

test.describe("Resilient list loads (demo mode success path)", () => {
  test("inbox renders without the error/retry banner", async ({ page }) => {
    await page.goto("/inbox");
    await expect(page.getByRole("heading", { name: /inbox/i, exact: false })).toBeVisible({ timeout: 10_000 });

    // Demo loads succeed, so the inbox error banner must not be shown.
    await expect(page.getByText(/couldn.t load your inbox/i)).toHaveCount(0);

    // The subtitle reports an ingested-messages count (list state, not error).
    await expect(page.getByText(/messages ingested/i)).toBeVisible({ timeout: 10_000 });
  });

  test("tasks renders the kanban without the error/retry banner", async ({ page }) => {
    await page.goto("/tasks");
    await expect(page.getByRole("heading", { name: /tasks/i, exact: false })).toBeVisible({ timeout: 10_000 });

    // Demo loads succeed, so the tasks error banner must not be shown.
    await expect(page.getByText(/couldn.t load your tasks/i)).toHaveCount(0);

    // Kanban column headers render (Open / In Progress / Done).
    await expect(page.getByRole("heading", { name: /open/i }).first()).toBeVisible({ timeout: 10_000 });
  });
});
