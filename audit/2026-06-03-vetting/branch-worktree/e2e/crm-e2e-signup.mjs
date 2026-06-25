// Step A: real UI signup; persist browser state (incl. PKCE verifier cookie).
import { chromium } from "@playwright/test";

const BASE = "https://www.riphere.com";
const EMAIL = process.env.E2E_EMAIL;

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();

await page.goto(`${BASE}/login`, { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Sign up" }).click();
await page.locator('input[type="email"]').fill(EMAIL);
await page.locator('input[type="password"]').fill("E2eTest!0603crm");
await page.getByRole("button", { name: "Create account" }).click();
await page.getByText("Account created! Check your email").waitFor({ timeout: 15000 });
console.log("PASS  UI signup complete:", EMAIL);

await context.storageState({ path: "/tmp/crm-e2e-state.json" });
console.log("PASS  browser state saved (PKCE verifier cookie preserved)");
await browser.close();
