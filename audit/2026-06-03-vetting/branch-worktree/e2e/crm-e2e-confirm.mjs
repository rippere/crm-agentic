// Step B: open the real confirmation link in the same browser state; assert
// the full GoTrue → /auth/callback → session → app chain. Then clean up.
import { chromium } from "@playwright/test";

const BASE = "https://www.riphere.com";
const SUPA = "https://ilfibxflnelssllgszex.supabase.co";
const SVC = process.env.SVC_KEY;
const EMAIL = process.env.E2E_EMAIL;
const LINK = process.env.CONFIRM_LINK;

const admin = (path, opts = {}) =>
  fetch(`${SUPA}/auth/v1${path}`, {
    ...opts,
    headers: { apikey: SVC, Authorization: `Bearer ${SVC}`, "Content-Type": "application/json" },
  }).then(async (r) => ({ status: r.status, body: await r.json().catch(() => null) }));

let failed = false;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
  if (!ok) failed = true;
};

import { existsSync } from "node:fs";
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext(
  existsSync("/tmp/crm-e2e-state.json") ? { storageState: "/tmp/crm-e2e-state.json" } : {},
);
const page = await context.newPage();
try {
  console.log("[e2e] clicking real confirmation link…");
  await page.goto(LINK, { waitUntil: "networkidle" });
  // Rescue path: hydrate → setSession → /dashboard → /onboarding can take a few hops.
  await page
    .waitForURL(/\/(onboarding|dashboard|login)/, { timeout: 25000 })
    .catch(() => {});
  await page.waitForTimeout(1500);

  const landed = page.url().split("#")[0];
  console.log("[e2e] landed on:", landed);

  if (/\/(onboarding|dashboard)/.test(landed)) {
    // Seamless variant (PKCE ?code= exchange) — already in the app.
    check("email link lands in app (seamless)", true, landed);
    const cookies = await context.cookies(BASE);
    const auth = cookies.find((c) => c.name.includes("-auth-token") && !c.name.includes("verifier"));
    check("authenticated session established", !!auth, auth?.name ?? "no auth cookie");
  } else if (landed.includes("/login")) {
    // Graceful variant (fragment tokens / cross-device) — banner + manual sign-in.
    check("email link reaches login fallback", landed.includes("confirmed=1"), landed);
    const banner = page.getByText("Email confirmed! Sign in to continue.");
    await banner.waitFor({ timeout: 10000 }).catch(() => {});
    check("confirmation banner shown", await banner.isVisible().catch(() => false));

    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill("E2eTest!0603crm");
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.waitForURL(/\/(onboarding|dashboard)/, { timeout: 20000 });
    check("sign-in after confirmation lands in app", true, page.url());
  } else {
    check("email link lands somewhere known", false, landed);
  }

  const heading = await page.locator("h1, h2").first().textContent().catch(() => "");
  console.log("[e2e] page heading:", JSON.stringify(heading));

  await page.screenshot({ path: "/tmp/crm-final-landing.png" });

  const res = await admin(`/admin/users?page=1&per_page=5&filter=${encodeURIComponent(EMAIL)}`);
  const user = res.body?.users?.find((u) => u.email === EMAIL);
  check("email_confirmed_at set", !!user?.email_confirmed_at, user?.email_confirmed_at);
  if (user) {
    const del = await admin(`/admin/users/${user.id}`, { method: "DELETE" });
    check("test user cleaned up", del.status === 200, `id=${user.id}`);
  }
} finally {
  await browser.close();
}
console.log(failed ? "RESULT: FAIL" : "RESULT: PASS");
process.exit(failed ? 1 : 0);
