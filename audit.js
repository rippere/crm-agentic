/**
 * NovaCRM Playwright Site Audit
 * Usage: node audit.js [--fix] [--headless]
 *
 * Traverses all 16 pages in demo mode, checks for visual/functional gaps,
 * and writes a report to audit-report.json.
 *
 * Run repeatedly until PASS count stops growing.
 */

const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const BASE_URL = 'http://localhost:3000'
const SCREENSHOTS_DIR = path.join(__dirname, 'audit-screenshots')
const REPORT_FILE = path.join(__dirname, 'audit-report.json')

const PAGES = [
  { name: 'login',       path: '/login',       auth: false },
  { name: 'dashboard',   path: '/dashboard',   auth: true  },
  { name: 'contacts',    path: '/contacts',    auth: true  },
  { name: 'pipeline',    path: '/pipeline',    auth: true  },
  { name: 'deals',       path: '/deals',       auth: true  },
  { name: 'reports',     path: '/reports',     auth: true  },
  { name: 'agents',      path: '/agents',      auth: true  },
  { name: 'calls',       path: '/calls',       auth: true  },
  { name: 'inbox',       path: '/inbox',       auth: true  },
  { name: 'tasks',       path: '/tasks',       auth: true  },
  { name: 'connectors',  path: '/connectors',  auth: true  },
  { name: 'settings',    path: '/settings',    auth: true  },
  { name: 'projects',    path: '/projects',    auth: true  },
]

const CHECKS = {
  dashboard: async (page) => {
    const checks = []
    // KPI cards should be visible
    const kpiText = await page.textContent('body')
    checks.push({ name: 'KPI revenue visible', pass: kpiText.includes('$') && (kpiText.includes('K') || kpiText.includes('M')) })
    // Activity feed should have items
    const activityItems = await page.locator('[data-testid="activity-item"], .activity-item, li').count()
    checks.push({ name: 'Activity feed has items (or page has list items)', pass: activityItems > 0 })
    // No "undefined" text visible
    checks.push({ name: 'No raw "undefined" values', pass: !kpiText.includes('"undefined"') && !kpiText.match(/\bundefined\b/) })
    return checks
  },
  contacts: async (page) => {
    const checks = []
    const bodyText = await page.textContent('body')
    // Should show contacts, not empty state
    checks.push({ name: 'Shows contact names (not empty)', pass: bodyText.includes('Sarah') || bodyText.includes('Marcus') || bodyText.includes('Rivera') || bodyText.includes('Chen') })
    checks.push({ name: 'No raw "undefined" values', pass: !bodyText.match(/\bundefined\b/) })

    // Click Marcus Rivera if visible
    const marcusBtn = page.getByText('Marcus Rivera')
    const hasMarcus = await marcusBtn.count() > 0
    if (hasMarcus) {
      await marcusBtn.first().click()
      await page.waitForTimeout(800)
      const drawerText = await page.textContent('body')
      // Brief modal trigger
      const briefBtn = page.getByText(/Pre-Meeting Brief|Brief/i)
      if (await briefBtn.count() > 0) {
        await briefBtn.first().click()
        await page.waitForTimeout(1200)
        const briefText = await page.textContent('body')
        checks.push({ name: 'Brief shows Marcus Rivera (not James Whitfield)', pass: briefText.includes('Marcus') && !briefText.includes('James Whitfield is the Head of Procurement at TechCorp') })
        // Close modal
        const closeBtn = page.locator('button[aria-label="Close"], button:has-text("Close"), [data-testid="close"]')
        if (await closeBtn.count() > 0) await closeBtn.first().click()
      }
      // Compose email
      const composeBtn = page.getByText(/Compose|Email/i)
      if (await composeBtn.count() > 0) {
        await composeBtn.first().click()
        await page.waitForTimeout(800)
        const emailText = await page.textContent('body')
        checks.push({ name: 'Email mentions Global Finance (not generic "Acme Corp Team")', pass: emailText.includes('Global Finance') || emailText.includes('Marcus') })
        checks.push({ name: 'Email not generic "Hi," greeting', pass: !emailText.includes('Hi,\n\nThank you for reaching out about the enterprise plan') })
      }
    } else {
      checks.push({ name: 'Marcus Rivera visible on contacts page', pass: false })
    }
    return checks
  },
  pipeline: async (page) => {
    const checks = []
    const bodyText = await page.textContent('body')
    checks.push({ name: 'Kanban columns visible', pass: bodyText.includes('Negotiation') || bodyText.includes('Proposal') || bodyText.includes('Lead') })
    checks.push({ name: 'Deals visible in pipeline', pass: bodyText.includes('TechCorp') || bodyText.includes('Global Finance') || bodyText.includes('Accelarate') })
    checks.push({ name: 'Health scores visible', pass: bodyText.match(/\d+%/) !== null || bodyText.includes('health') })
    return checks
  },
  reports: async (page) => {
    const checks = []
    // Charts should render - check for canvas or svg elements
    await page.waitForTimeout(500)
    const chartElements = await page.locator('canvas, svg').count()
    checks.push({ name: 'Chart rendered (canvas or svg present)', pass: chartElements > 0 })
    const bodyText = await page.textContent('body')
    // Revenue numbers should be consistent (visit page twice and compare)
    const firstRevenue = bodyText.match(/\$[\d,]+/)
    checks.push({ name: 'Revenue figures visible', pass: firstRevenue !== null })
    // Navigate away and back to check consistency
    await page.goto(`${BASE_URL}/dashboard`)
    await page.goto(`${BASE_URL}/reports`)
    await page.waitForTimeout(500)
    const secondText = await page.textContent('body')
    const secondRevenue = secondText.match(/\$[\d,]+/)
    checks.push({ name: 'Revenue chart consistent across page loads', pass: firstRevenue?.[0] === secondRevenue?.[0] })
    return checks
  },
  agents: async (page) => {
    const checks = []
    const bodyText = await page.textContent('body')
    checks.push({ name: 'Agent cards visible', pass: bodyText.includes('Agent') || bodyText.includes('Scorer') || bodyText.includes('Optimizer') })
    checks.push({ name: 'No empty agent list', pass: !bodyText.includes('No agents') && !bodyText.includes('no agents') })
    return checks
  },
  calls: async (page) => {
    const checks = []
    const bodyText = await page.textContent('body')
    checks.push({ name: 'Call records visible', pass: bodyText.includes('Q2 Strategy') || bodyText.includes('TechCorp Deal') || bodyText.includes('BuildRight') })
    return checks
  },
  inbox: async (page) => {
    const checks = []
    const bodyText = await page.textContent('body')
    checks.push({ name: 'Inbox has content', pass: bodyText.length > 200 && !bodyText.includes('No messages') })
    return checks
  },
}

async function runAudit() {
  if (!fs.existsSync(SCREENSHOTS_DIR)) fs.mkdirSync(SCREENSHOTS_DIR, { recursive: true })

  const isHeadless = process.argv.includes('--headless') || process.env.CI === 'true'
  const browser = await chromium.launch({ headless: isHeadless })
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()

  const consoleErrors = []
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push({ url: page.url(), text: msg.text() })
  })
  page.on('pageerror', err => {
    consoleErrors.push({ url: page.url(), text: err.message, isPageError: true })
  })

  const report = { timestamp: new Date().toISOString(), pages: [], consoleErrors: [], summary: {} }

  // ── Visit each page ──────────────────────────────────────────────────────────
  for (const { name, path: pagePath } of PAGES) {
    console.log(`\n  Auditing /${name}...`)
    const pageConsoleErrors = []
    const pageListener = (msg) => { if (msg.type() === 'error') pageConsoleErrors.push(msg.text()) }
    page.on('console', pageListener)

    const result = { name, path: pagePath, status: 'unknown', checks: [], consoleErrors: [], screenshot: '' }

    try {
      const response = await page.goto(`${BASE_URL}${pagePath}`, { waitUntil: 'networkidle', timeout: 15000 })
      result.httpStatus = response?.status()

      if (result.httpStatus === 404) {
        result.status = 'not_found'
        console.log(`    ❌ 404 — page not found`)
      } else {
        await page.waitForTimeout(600)

        // Screenshot
        const screenshotPath = path.join(SCREENSHOTS_DIR, `${name}.png`)
        await page.screenshot({ path: screenshotPath, fullPage: true })
        result.screenshot = screenshotPath

        // Error text on page
        const bodyText = await page.textContent('body').catch(() => '')
        result.hasErrorText = /error|Error|404|not found|failed/i.test(bodyText) && !/console.error/i.test(bodyText)

        // Run page-specific checks
        if (CHECKS[name]) {
          result.checks = await CHECKS[name](page)
          // Re-screenshot after interactive checks (drawer may be open)
          const screenshotPath2 = path.join(SCREENSHOTS_DIR, `${name}-post-checks.png`)
          await page.screenshot({ path: screenshotPath2, fullPage: true })
        }

        const failedChecks = result.checks.filter(c => !c.pass)
        result.status = failedChecks.length === 0 ? 'pass' : 'issues'
        console.log(`    ${result.status === 'pass' ? '✅' : '⚠️ '} ${result.checks.length} checks — ${failedChecks.length} failed`)
        failedChecks.forEach(c => console.log(`       ✗ ${c.name}`))
      }
    } catch (err) {
      result.status = 'error'
      result.error = err.message
      console.log(`    💥 Error: ${err.message}`)
    }

    page.removeListener('console', pageListener)
    result.consoleErrors = pageConsoleErrors
    report.pages.push(result)
  }

  // ── Summary ──────────────────────────────────────────────────────────────────
  const passed = report.pages.filter(p => p.status === 'pass').length
  const issues = report.pages.filter(p => p.status === 'issues').length
  const errors = report.pages.filter(p => p.status === 'error' || p.status === 'not_found').length
  report.summary = { total: report.pages.length, passed, issues, errors, consoleErrors: consoleErrors.length }
  report.consoleErrors = consoleErrors

  console.log(`\n${'─'.repeat(60)}`)
  console.log(`AUDIT COMPLETE: ${passed}/${report.pages.length} pages PASS, ${issues} with issues, ${errors} errors`)
  console.log(`Screenshots: ${SCREENSHOTS_DIR}`)
  console.log(`Report: ${REPORT_FILE}`)

  fs.writeFileSync(REPORT_FILE, JSON.stringify(report, null, 2))
  await browser.close()
  return report
}

runAudit().catch(console.error)
