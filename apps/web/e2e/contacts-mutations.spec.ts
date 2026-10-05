import { test, expect, type Page } from "@playwright/test";

// Runs in demo mode (NEXT_PUBLIC_DEMO_MODE=true). Demo contacts: 4 customers,
// 3 prospects, 2 leads (Priya Nair, Devon Park), 1 churned — 10 total.
//
// Regression for onboarding item #2: bulk Set Status / Delete hit the API but
// never updated the list, so the badge and stat cards stayed stale until a
// full reload.

function statCard(page: Page, label: string) {
  // Stat cards are buttons whose text is "<count><label>", e.g. "4Customers".
  return page.getByRole("button", { name: new RegExp(`^\\d+\\s*${label}$`, "i") });
}

function contactRow(page: Page, name: string) {
  return page.locator("tbody tr").filter({ hasText: name });
}

async function selectRow(page: Page, name: string) {
  await contactRow(page, name).getByRole("button", { name: "Select contact" }).click();
}

test.describe("Contacts list reflects mutations without a reload", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/contacts");
    await expect(contactRow(page, "Priya Nair")).toBeVisible({ timeout: 10_000 });
  });

  test("bulk Set Status updates the badge and stat cards", async ({ page }) => {
    const row = contactRow(page, "Priya Nair");
    await expect(row.getByText("Lead", { exact: true })).toBeVisible();
    await expect(statCard(page, "Customers")).toHaveText(/^4/);
    await expect(statCard(page, "Leads")).toHaveText(/^2/);

    await selectRow(page, "Priya Nair");
    await page.getByRole("button", { name: "Set Status" }).click();
    await page.getByRole("button", { name: "customer", exact: true }).click();

    await expect(row.getByText("Customer", { exact: true })).toBeVisible({ timeout: 3_000 });
    await expect(statCard(page, "Customers")).toHaveText(/^5/, { timeout: 3_000 });
    await expect(statCard(page, "Leads")).toHaveText(/^1/);
    await expect(statCard(page, "Total")).toHaveText(/^10/);
  });

  test("a row that no longer matches the status filter drops out", async ({ page }) => {
    // The click auto-waits a few seconds while the product tour overlay settles.
    await statCard(page, "Leads").click();
    await expect(page.locator("tbody tr")).toHaveCount(2);

    await selectRow(page, "Priya Nair");
    await page.getByRole("button", { name: "Set Status" }).click();
    await page.getByRole("button", { name: "customer", exact: true }).click();

    await expect(contactRow(page, "Priya Nair")).toHaveCount(0, { timeout: 3_000 });
    await expect(contactRow(page, "Devon Park")).toBeVisible();
  });

  test("bulk Delete removes the row and updates the totals", async ({ page }) => {
    await expect(statCard(page, "Total")).toHaveText(/^10/);

    await selectRow(page, "Priya Nair");
    await page.getByRole("button", { name: "Delete", exact: true }).click();
    await page.getByRole("button", { name: "Delete 1 contact" }).click();

    await expect(contactRow(page, "Priya Nair")).toHaveCount(0, { timeout: 3_000 });
    await expect(statCard(page, "Total")).toHaveText(/^9/);
    await expect(statCard(page, "Leads")).toHaveText(/^1/);
  });
});
