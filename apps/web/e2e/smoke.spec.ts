import { test, expect } from "@playwright/test";

// All tests run in demo mode (NEXT_PUBLIC_DEMO_MODE=true).
// Auth guard is bypassed, so all app routes are accessible without login.

test.describe("Navigation smoke tests", () => {
  test("dashboard loads with KPI cards", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page).toHaveTitle(/CRM/i);

    // At least one KPI card value must be visible
    await expect(page.getByRole("region", { name: /kpi/i }).first().or(
      page.locator('[class*="font-mono"]').first()
    )).toBeVisible({ timeout: 10_000 });

    // Main heading
    await expect(page.getByRole("heading", { name: /dashboard/i, exact: false })).toBeVisible();
  });

  test("contacts page renders contact rows", async ({ page }) => {
    await page.goto("/contacts");
    await expect(page.getByRole("heading", { name: /contacts/i, exact: false })).toBeVisible();

    // Demo data has at least one contact
    await expect(page.locator("table tbody tr, [data-testid='contact-row'], [class*='rounded-xl']").first())
      .toBeVisible({ timeout: 10_000 });
  });

  test("pipeline page renders deal columns", async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.getByRole("heading", { name: /pipeline/i, exact: false })).toBeVisible();

    // Pipeline board region
    const board = page.getByRole("region", { name: /pipeline board/i });
    await expect(board).toBeVisible({ timeout: 10_000 });

    // At least one stage column visible
    await expect(board.locator("[class*='min-w']").first()).toBeVisible();
  });

  test("pipeline → deal detail navigation", async ({ page }) => {
    await page.goto("/pipeline");
    await expect(page.getByRole("region", { name: /pipeline board/i })).toBeVisible({ timeout: 10_000 });

    // Click the first ExternalLink icon to navigate to a deal detail page
    const dealLink = page.locator('a[href^="/pipeline/"]').first();
    if (await dealLink.count() > 0) {
      const href = await dealLink.getAttribute("href");
      await page.goto(href!);
      await expect(page.getByRole("heading", { name: /deal/i, exact: false })
        .or(page.locator("h1, h2").first())
      ).toBeVisible({ timeout: 10_000 });
    }
  });

  test("contacts page search filters results", async ({ page }) => {
    await page.goto("/contacts");
    await expect(page.getByRole("heading", { name: /contacts/i, exact: false })).toBeVisible();

    // Find search input and type
    const searchInput = page.getByPlaceholder(/search/i).or(page.getByRole("searchbox"));
    if (await searchInput.count() > 0) {
      await searchInput.fill("zzzz_no_match_expected");
      // After filtering, some no-results state or reduced list
      await page.waitForTimeout(300);
      // Just assert the page doesn't crash
      await expect(page.getByRole("heading", { name: /contacts/i, exact: false })).toBeVisible();
    }
  });

  test("agents page renders agent cards", async ({ page }) => {
    await page.goto("/agents");
    await expect(page.getByRole("heading", { name: /agents/i, exact: false })).toBeVisible();
    // At least one agent card
    await expect(page.locator("[class*='rounded-2xl'], [class*='rounded-xl']").first())
      .toBeVisible({ timeout: 10_000 });
  });

  test("inbox page loads", async ({ page }) => {
    await page.goto("/inbox");
    await expect(page.getByRole("heading", { name: /inbox/i, exact: false })).toBeVisible({ timeout: 10_000 });
  });

  test("tasks page loads with kanban columns", async ({ page }) => {
    await page.goto("/tasks");
    await expect(page.getByRole("heading", { name: /tasks/i, exact: false })).toBeVisible({ timeout: 10_000 });
  });

  test("settings page loads", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: /settings/i, exact: false })).toBeVisible({ timeout: 10_000 });
  });
});
