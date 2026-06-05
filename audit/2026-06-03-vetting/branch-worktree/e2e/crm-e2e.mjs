// Production e2e: NovaCRM signup → email-confirm callback → in-app landing.
// Run: SVC_KEY=... node /tmp/crm-e2e.mjs
import { chromium } from "@playwright/test";

const BASE = "https://www.riphere.com";
const SUPA = "https://ilfibxflnelssllgszex.supabase.co";
const SVC = process.env.SVC_KEY;
const EMAIL = `rippere.ben.r+crm-e2e-${process.env.RUN_TAG ?? "0603"}@gmail.com`;
const PASSWORD = "E2eTest!0603crm";

const admin = (path, opts = {}) =>
  fetch(`${SUPA}/auth/v1${path}`, {
    ...opts,
    headers: {
      apikey: SVC,
      Authorization: `Bearer ${SVC}`,
      "Content-Type": "application/json",
      ...opts.headers,
    },
  }).then(async (r) => ({ status: r.status, body: await r.json().catch(() => null) }));

const log = (...a) => console.log("[e2e]", ...a);
let failed = false;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
  if (!ok) failed = true;
};

// ── 0. Pre-clean: delete the test user if left over from a prior run ─────────
const pre = await admin(`/admin/users?page=1&per_page=5&filter=${encodeURIComponent(EMAIL)}`);
const preUser = pre.body?.users?.find((u) => u.email === EMAIL);
if (preUser) {
  await admin(`/admin/users/${preUser.id}`, { method: "DELETE" });
  log("pre-cleaned leftover test user", preUser.id);
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
try {
  // ── 1. Signup through the real UI ───────────────────────────────────────────
  await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
  check("login page loads", (await page.title()) !== "", `url=${page.url()}`);

  await page.getByRole("button", { name: "Sign up" }).click();
  await page.getByLabel("Email").fill(EMAIL).catch(async () => {
    await page.locator('input[type="email"]').fill(EMAIL);
  });
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  const confirmMsg = page.getByText("Account created! Check your email");
  await confirmMsg.waitFor({ timeout: 15000 });
  check("signup submits, confirmation message shown", true);

  // ── 2. Mint the confirmation token via admin API (no inbox needed) ──────────
  let gen = await admin("/admin/generate_link", {
    method: "POST",
    body: JSON.stringify({ type: "signup", email: EMAIL, password: PASSWORD }),
  });
  if (gen.status !== 200) {
    log("generate_link(signup) failed:", gen.status, JSON.stringify(gen.body));
    gen = await admin("/admin/generate_link", {
      method: "POST",
      body: JSON.stringify({ type: "magiclink", email: EMAIL }),
    });
  }
  const { hashed_token, verification_type, action_link } = gen.body ?? {};
  check("admin minted confirmation token", !!hashed_token, `type=${verification_type}`);
  log("action_link redirect_to:", decodeURIComponent(action_link?.split("redirect_to=")[1] ?? "?"));

  // ── 3. Drive the callback exactly as the email link would ───────────────────
  await page.goto(
    `${BASE}/auth/callback?token_hash=${hashed_token}&type=${verification_type}`,
    { waitUntil: "networkidle" },
  );
  await page.waitForTimeout(2000); // allow client-side router redirects to settle
  const landed = page.url();
  log("landed on:", landed);
  const onOnboardingOrDash = /\/(onboarding|dashboard)/.test(landed);
  check("callback lands in app (onboarding/dashboard)", onOnboardingOrDash, landed);

  const heading = await page.locator("h1, h2").first().textContent().catch(() => "");
  log("page heading:", JSON.stringify(heading));
  await page.screenshot({ path: "/tmp/crm-e2e-landing.png" });

  // ── 4. Session actually established? (auth cookies present) ────────────────
  const cookies = await page.context().cookies(BASE);
  const authCookie = cookies.find((c) => c.name.includes("-auth-token"));
  check("supabase auth session cookie set", !!authCookie, authCookie?.name ?? "none");

  // ── 5. Email confirmed server-side? ─────────────────────────────────────────
  const post = await admin(`/admin/users?page=1&per_page=5&filter=${encodeURIComponent(EMAIL)}`);
  const user = post.body?.users?.find((u) => u.email === EMAIL);
  check("email_confirmed_at set", !!user?.email_confirmed_at, user?.email_confirmed_at);

  // ── 6. Cleanup: remove the e2e user ─────────────────────────────────────────
  if (user) {
    const del = await admin(`/admin/users/${user.id}`, { method: "DELETE" });
    check("test user cleaned up", del.status === 200, `id=${user.id}`);
  }
} finally {
  await browser.close();
}
console.log(failed ? "RESULT: FAIL" : "RESULT: PASS");
process.exit(failed ? 1 : 0);
