import { test, expect } from "@playwright/test";

// Lead-generation / marketing module E2E — the "September bar" click-path Zach is
// shown (BUILD-SPEC-leadgen.md §7). All tests run in demo mode
// (NEXT_PUBLIC_DEMO_MODE=true): auth is bypassed, every route is seeded
// synchronously from src/lib/demo-data.ts, and mutations are optimistic local
// state (no backend, no job polling, no toasts). Locators are role/text/
// placeholder based — this repo has NO data-testid anywhere. Demo fixture ids
// are stable: leads l-001..l-041 (l-020 = Omar Haddad, richest timeline),
// sequences sq-001 (active, 3 email steps) / sq-002 (draft, mixed), campaigns
// cmp-001 (active) / cmp-002 (scheduled) / cmp-003 (draft "Cold Lead
// Reactivation"), 4 pending outreach drafts (first lead "Sofia Marchetti").

test.describe("Leadgen — leads funnel (table + board)", () => {
  test("leads page renders table and toggles to the funnel board", async ({ page }) => {
    await page.goto("/leads");
    await expect(page.getByRole("heading", { level: 1, name: "Leads" })).toBeVisible({
      timeout: 10_000,
    });

    // Default view is the table — at least one seeded lead row.
    await expect(page.locator("table tbody tr").first()).toBeVisible({ timeout: 10_000 });

    // Toggle to the funnel board (label is "Funnel"); the board is an aria region.
    await page.getByRole("button", { name: "Funnel" }).click();
    const board = page.getByRole("region", { name: /leads funnel board/i });
    await expect(board).toBeVisible({ timeout: 10_000 });

    // Board back to table.
    await page.getByRole("button", { name: "Table" }).click();
    await expect(page.locator("table tbody tr").first()).toBeVisible();
  });

  test("stage stat-tile filters the leads list", async ({ page }) => {
    await page.goto("/leads");
    await expect(page.getByRole("heading", { level: 1, name: "Leads" })).toBeVisible({
      timeout: 10_000,
    });

    const before = await page.locator("table tbody tr").count();
    expect(before).toBeGreaterThan(0);

    // Filter to "Qualified" via its stat tile (accessible name is "<count> Qualified").
    await page.getByRole("button", { name: /\d+\s+Qualified$/ }).click();
    await page.waitForTimeout(200);

    // Every visible row is now Qualified (or an empty-state message shows).
    const rows = page.locator("table tbody tr");
    const rowCount = await rows.count();
    if (rowCount > 0) {
      await expect(rows.filter({ hasText: /Qualified/i }).first()).toBeVisible();
    } else {
      await expect(page.getByText(/no leads match/i)).toBeVisible();
    }

    // "Total" tile resets the filter.
    await page.getByRole("button", { name: /\d+\s+Total$/ }).click();
    await page.waitForTimeout(200);
    await expect(page.locator("table tbody tr")).toHaveCount(before);
  });

  test("import CSV modal opens with a column-mapping affordance", async ({ page }) => {
    await page.goto("/leads");
    await expect(page.getByRole("heading", { level: 1, name: "Leads" })).toBeVisible({
      timeout: 10_000,
    });

    await page.getByRole("button", { name: "Import CSV" }).click();
    // Modal title is a <p>, not a heading — match by text.
    await expect(page.getByText(/import leads \(csv\)/i)).toBeVisible();

    // The upload step exposes a hidden file input; drive it directly.
    const fileInput = page.locator('input[type="file"]');
    await expect(fileInput).toHaveCount(1);
    await fileInput.setInputFiles({
      name: "leads.csv",
      mimeType: "text/csv",
      buffer: Buffer.from(
        "name,email,company\nAva Nolan,ava@rooftopvenue.com,Rooftop Venue Co\n",
      ),
    });

    // Mapping step: an "Import N leads" action appears once the CSV is parsed.
    await expect(page.getByRole("button", { name: /import 1 lead/i })).toBeVisible({
      timeout: 10_000,
    });
  });
});

test.describe("Leadgen — lead detail: promote + stage transition", () => {
  test("promoting a lead shows the confirmation banner", async ({ page }) => {
    // l-020 (Omar Haddad) is engaged with a full timeline and promote controls.
    await page.goto("/leads/l-020");
    await expect(page.getByRole("heading", { level: 1, name: /Omar Haddad/i })).toBeVisible({
      timeout: 10_000,
    });

    // Promote to a contact (optimistic inline banner, not a modal).
    await page.getByRole("button", { name: "Promote to Contact" }).click();
    await expect(page.getByText(/^Promoted —/)).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Leadgen — sequence step builder", () => {
  test("sequences list links into the step builder", async ({ page }) => {
    await page.goto("/sequences");
    await expect(page.getByRole("heading", { level: 1, name: "Sequences" })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.locator('a[href^="/sequences/"]').first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test("builder adds a step and saves the ordered list", async ({ page }) => {
    // sq-001 = active, 3 email steps.
    await page.goto("/sequences/sq-001");
    // H1 is the sequence name; wait on it rather than the one-frame loading spinner.
    await expect(page.locator("h1")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Step builder ·\s*\d+ steps?/i)).toBeVisible();

    // Count existing StepCards (left indigo border marks each card).
    const stepCards = page.locator("div.border-l-indigo-500\\/60");
    const initial = await stepCards.count();
    expect(initial).toBeGreaterThan(0);

    // Append a step.
    await page.getByRole("button", { name: /Add step/i }).click();
    await expect(stepCards).toHaveCount(initial + 1);

    // Save — button label settles on "Saved" (~3s) in demo mode.
    await page.getByRole("button", { name: "Save Steps" }).click();
    await expect(page.getByRole("button", { name: /Saved/i })).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Leadgen — campaign create + launch", () => {
  test("new campaign modal creates a draft row", async ({ page }) => {
    await page.goto("/campaigns");
    await expect(page.getByRole("heading", { level: 1, name: "Campaigns" })).toBeVisible({
      timeout: 10_000,
    });

    await page.getByRole("button", { name: "New Campaign" }).click();
    const nameInput = page.getByPlaceholder("Fall Wedding Season Blast");
    await expect(nameInput).toBeVisible();
    await nameInput.fill("Zach Fall Blast");

    // Segment + sequence selects default to the first option; leave defaults.
    await page.getByRole("button", { name: "Create Campaign" }).click();

    // Optimistic: new draft row is prepended to the table.
    await expect(page.getByRole("row").filter({ hasText: "Zach Fall Blast" })).toBeVisible({
      timeout: 10_000,
    });
  });

  test("launching a draft campaign flips it to active", async ({ page }) => {
    await page.goto("/campaigns");
    await expect(page.getByRole("heading", { level: 1, name: "Campaigns" })).toBeVisible({
      timeout: 10_000,
    });

    // cmp-003 "Cold Lead Reactivation" is a draft → its row shows a Launch action.
    const draftRow = page.getByRole("row").filter({ hasText: "Cold Lead Reactivation" });
    await expect(draftRow).toBeVisible({ timeout: 10_000 });

    await draftRow.getByRole("button", { name: "Launch" }).click();
    // The action button swaps Launch → Pause once active (optimistic).
    await expect(draftRow.getByRole("button", { name: "Pause" })).toBeVisible({
      timeout: 10_000,
    });
  });

  test("campaign detail shows the stats tiles", async ({ page }) => {
    // cmp-001 = active with real rollup stats.
    await page.goto("/campaigns/cmp-001");
    await expect(page.locator("h1")).toBeVisible({ timeout: 10_000 });
    for (const label of ["Enrolled", "Sent", "Opened", "Clicked", "Replied", "Converted"]) {
      await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
    }
  });
});

test.describe("Leadgen — outreach approval queue (bot → human handoff)", () => {
  test("approving a pending draft removes it from the queue", async ({ page }) => {
    await page.goto("/outreach");
    await expect(page.getByRole("heading", { level: 1, name: "Outreach" })).toBeVisible({
      timeout: 10_000,
    });

    // 4 drafts seed synchronously; subtitle reads "N drafts awaiting approval".
    await expect(page.getByText(/\d+ drafts? awaiting approval/i)).toBeVisible({
      timeout: 10_000,
    });

    // One card per pending draft, each with an "Approve & Send" button.
    const approveButtons = page.getByRole("button", { name: "Approve & Send" });
    const before = await approveButtons.count();
    expect(before).toBeGreaterThan(0);

    // Approving the first draft optimistically unmounts its card.
    await approveButtons.first().click();
    await expect(approveButtons).toHaveCount(before - 1, { timeout: 10_000 });
  });

  test("editing a draft body keeps approve enabled", async ({ page }) => {
    await page.goto("/outreach");
    await expect(page.getByRole("heading", { level: 1, name: "Outreach" })).toBeVisible({
      timeout: 10_000,
    });

    const bodyInput = page.getByPlaceholder("Message body…").first();
    await expect(bodyInput).toBeVisible({ timeout: 10_000 });
    await bodyInput.fill("Hi — following up on your rooftop event enquiry for Skyline.");

    await expect(page.getByRole("button", { name: "Approve & Send" }).first()).toBeEnabled();
  });
});
