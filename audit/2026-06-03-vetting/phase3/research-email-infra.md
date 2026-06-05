# Research: Auth / Transactional Email Infrastructure for SaaS (2026)
**Lens owner:** NovaCRM external-validation team
**Date:** 2026-06-03
**Product context:** NovaCRM — Next.js 16 + FastAPI + Supabase (auth+Postgres+RLS) on Railway. Uses Supabase Auth with PKCE email verification (per project memory: "Close out PKCE real-email verification" is an open carry-over task). Landing page claims SOC 2 Type II, 99.9% uptime, GDPR.

> Convention below: **SAY** = directly stated by a source. **INFER** = my analysis/extrapolation for NovaCRM. Vendor-biased sources flagged.

---

## 1. Supabase built-in SMTP limits & the custom-SMTP requirement

### What the official Supabase docs SAY
- **Built-in SMTP is non-production by design.** Three hard restrictions (Supabase Auth SMTP docs):
  1. **Pre-authorized addresses only** — built-in email only delivers to addresses belonging to team members in your Supabase org. Any other recipient fails with `Email address not authorized`. *(This is the single most important gotcha: a real signup from a stranger's email simply will not be delivered on built-in SMTP.)*
  2. **Significant rate limits** that "can change over time." The docs render the number as a template variable (`auth.rate_limits.email.inbuilt_smtp_per_hour`) rather than a literal — but every secondary source consistently reports the concrete value as **2 emails/hour**.
  3. **No SLA** on delivery or uptime — "best-effort only," intended for exploring/testing templates/toy projects.
- **Custom SMTP starts throttled.** On first configuring custom SMTP, Supabase imposes **"a low rate-limit of 30 messages per hour"** to protect sender reputation; you raise it on the Rate Limits config page. (Supabase Auth SMTP docs.)
- **After custom SMTP, limits are yours to set** (governed by your provider + the Supabase rate-limit config), not Supabase's 2/hr cap.
- **Required custom-SMTP settings:** host, port, user, password, default "From" address (e.g. `no-reply@example.com`), optional sender name.
- **Providers Supabase explicitly lists as compatible:** Resend, AWS SES, Postmark, Twilio SendGrid, ZeptoMail, Brevo.

### Concrete numbers confirmed by secondary sources
- Built-in = **2 emails/hour**, "not meant for production use" (Pingram, Dreamlit, multiple).
- Custom SMTP default = **30/hour** (≈ "30 new users/hour") until raised (search-confirmed across Supabase docs + tutorials).

### Other Supabase Auth rate limits (configurable via Management API / dashboard)
Params: `rate_limit_email_sent`, `rate_limit_sms_sent`, `rate_limit_verify`, `rate_limit_token_refresh`, `rate_limit_otp`, `rate_limit_anonymous_users`, `rate_limit_web3`. IP-based limits use a burst capacity of ~30 requests. Exact per-hour values are templated in docs, not literal.

### INFER for NovaCRM
- If NovaCRM is on built-in SMTP, **its public signup flow is effectively broken for anyone outside the dev's Supabase org** — strangers' confirmation emails are silently dropped (`Email address not authorized`), not merely rate-limited. This is the prime suspect behind any "I never got my confirmation email" report and the open PKCE-verification task. **Custom SMTP is mandatory, not optional, for a live product at riphere.com.**
- A 99.9%-uptime landing claim is inconsistent with relying on Supabase's no-SLA best-effort built-in mailer for auth.

**Sources:**
- https://supabase.com/docs/guides/auth/auth-smtp
- https://supabase.com/docs/guides/auth/rate-limits
- https://www.pingram.io/blog/how-to-send-emails-with-supabase
- https://www.pingram.io/blog/best-smtp-providers-for-supabase
- https://dreamlit.ai/blog/how-to-send-emails-supabase
- https://github.com/orgs/supabase/discussions/16209 (429 email rate limit w/ custom SMTP)
- https://github.com/orgs/supabase/discussions/15896 (notice: change to email rate limits)
- https://supabase.com/docs/guides/deployment/going-into-prod (production checklist)

---

## 2. Resend vs Postmark vs SES (vs SendGrid / Brevo) for transactional auth email

### Pricing & free tiers (June 2026)
| Provider | Permanent free tier | Daily cap on free | Paid entry | $/1k at scale | Notes |
|---|---|---|---|---|---|
| **Resend** | **3,000/mo** | **100/day** | Pro $20/mo (→$35) | ~$0.40/1k | 1 verified domain on free; 30-day log retention; routes via SES under the hood |
| **Postmark** | **None** (100/mo trial only) | — | $15/mo (10k) | ~$1.50/1k | Own infra; Message Streams separate txn vs broadcast |
| **Amazon SES** | 3,000/mo **first 12 mo only** | — | pay-as-you-go | **$0.10/1k** (cheapest) | You build dashboard/templates/suppression/warmup |
| **SendGrid** | **KILLED 2025-05-27** | 60-day trial 100/day | $19.95/mo (100k/Email API) | — | Permanent free plan retired by Twilio |
| **Brevo** | 300/day | 300/day | tiered | — | Best *free* SendGrid alternative by daily allowance |
| **Mailtrap** | 4,000/mo | — | $15/mo (10k) | — | ISO 27001 + SOC 2; separate streams |

### Deliverability (NEUTRAL benchmark — Mailtrap inbox-placement testing, balances vendor bias)
- **Postmark 83.3%** inbox placement (highest tested)
- **Mailtrap 78.8%**
- **Amazon SES 77.1%**
> These are the most neutral comparative deliverability numbers found. Treat as directional, not gospel.

### Postmark's own claims (VENDOR-BIASED — Postmark comparing itself to Resend)
- Resend routes 100% through Amazon SES → "every Resend email is queued twice" → extra latency on password resets / OTPs.
- Knock-benchmark figures cited by Postmark: **Postmark 33ms vs Resend 79ms** median API response; **0.00% vs 0.07%** daily error rate; **45-day vs 3-day** retention.
- Stream separation: Resend mixes txn + broadcast on shared SES pools → "a spike in broadcast complaints could affect your password-reset deliverability." Postmark isolates via Message Streams.
- Human support on every plan, <2h avg response; pre-built tested transactional templates; spam-score checking; 16 yrs managed IP reputation.
> Caveat: this is Postmark's marketing page. The *architecture* facts (Resend = SES wrapper; shared pools; SES needs you to build tooling) are corroborated by neutral sources; the *latency/error* numbers are Postmark-selected and should be treated skeptically.

### SES setup effort (the real cost of "cheapest")
- New SES accounts start in a **sandbox**: can only send to verified addresses, low quota — same class of problem as Supabase built-in.
- **Production access** = a manual AWS request: describe the company, 1–2 use cases w/ sample emails, list-building method, peak TPS; set up SPF/DKIM/DMARC + bounce/complaint handling (via SNS) **before** asking. No mandatory wait, usually approved quickly, but it's a one-time hurdle.
- Sending-reputation gates: keep **bounce <5%, complaint <0.1%**.
- Setup-time estimates: SES **30+ min**; Resend **~10 min**; Postmark **~10 min**; SendGrid **~15 min**; one-click integrations (Pingram) **~2 min**.

### INFER for NovaCRM (solo dev, low current volume)
- At NovaCRM's stage, auth-email volume is tiny (signup confirms, password resets, magic links). **The decision is dominated by setup effort + deliverability + free-tier fit, NOT per-email cost.** SES's $0.10/1k advantage is irrelevant below ~tens of thousands/mo and is outweighed by sandbox friction + DIY tooling.
- **Resend is the lowest-friction fit:** official Supabase integration (auto-fills SMTP creds + creates API key), 3,000/mo free covers a solo-dev launch, ~10-min setup, listed first-party by both Supabase and Resend.
- **Postmark is the deliverability-max / reset-reliability choice** if the dev is willing to pay $15/mo from day one (no free tier) and values stream separation + human support. Strong argument specifically because auth email is exactly the "must arrive, must arrive fast" category Postmark optimizes for.
- The 100/day cap on Resend free is the usual reason teams upgrade — **fine for NovaCRM now, but a launch-day signup spike or a marketing blast could hit it.** Worth knowing before a Product Hunt / demo-day moment.

**Sources:**
- https://postmarkapp.com/compare/resend-alternative (vendor-biased)
- https://mailtrap.io/blog/transactional-email-services/ (neutral deliverability benchmarks)
- https://www.buildmvpfast.com/api-costs/email
- https://blog.vibecoder.me/email-service-pricing-resend-sendgrid-postmark
- https://resend.com/pricing , https://resend.com/docs/knowledge-base/account-quotas-and-limits , https://resend.com/blog/new-free-tier
- https://nuntly.com/resend-pricing
- https://automationatlas.io/answers/resend-free-tier-explained-2026/
- https://dev.to/thiago_alvarez_a7561753aa/resend-vs-sendgrid-2026-sendgrid-killed-its-free-tier-now-what-2gh4 (SendGrid free-tier retirement)
- https://dreamlit.ai/blog/best-sendgrid-alternatives
- https://www.brevo.com/blog/sendgrid-alternatives/
- SES production access: https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html , https://oneuptime.com/blog/post/2026-02-12-move-amazon-ses-out-of-sandbox/view , https://bluefox.email/aws-concepts/ses-sandbox

---

## 3. Supabase + Resend custom-SMTP setup (concrete recipe)

### What the Resend/Supabase docs SAY
- **SMTP creds (manual):** host `smtp.resend.com`, port `465`, username `resend`, password = your Resend API key. Set sender email + name (e.g. `support@example.com` / "ACME Support") in Supabase → Authentication → Notifications → Email → SMTP Settings.
- **One-click integration exists:** Supabase Integrations page → connect Resend → it auto-creates a Resend API key and auto-fills Supabase's SMTP settings.
- **Domain verification (SPF/DKIM/DMARC) is required on the Resend side** before sending from your own domain — the Supabase-side doc page doesn't restate this, so it's a known footgun to consult Resend's domain-verification docs. By default unconfigured Supabase auth mail comes from `noreply@mail.app.supabase.io`; custom SMTP lets you send from your own domain for brand/deliverability.
- After enabling custom SMTP, **raise the Supabase auth email rate limit** off the default 30/hr to match real signup throughput (otherwise you'll throw `429 Email rate limit exceeded` even though the provider could deliver — see Supabase Discussion #16209).

### INFER for NovaCRM
- Concrete, ~10-minute migration path exists; the only non-obvious steps are (a) DNS records for domain auth and (b) bumping the Supabase 30/hr limit. Both are one-time.

**Sources:**
- https://resend.com/docs/send-with-supabase-smtp
- https://resend.com/blog/how-to-configure-supabase-to-send-emails-from-your-domain
- https://supabase.com/partners/integrations/resend
- https://brucelim.com/blog/setting-up-supabase-auth-with-resend-smtp
- https://github.com/orgs/supabase/discussions/16209

---

## 4. Email-prefetch / link-consumption — HIGH-IMPACT for NovaCRM's PKCE flow

### What sources SAY
- **The #1 cause of "token already expired/invalid before the user clicked" is email prefetching** — security tools/email clients that auto-scan URLs in inbound mail and thereby *consume* a single-use confirmation/OTP token before the human acts. (Supabase troubleshooting: "OTP Verification Failures: token has expired / otp_expired".)
- **Microsoft Outlook / Defender "Safe Links"** rewrites inbound URLs to `*.safelinks.protection.outlook.com` and does **time-of-click + scan-time** verification, issuing **GET** (not HEAD) requests — which triggers Supabase's code exchange and burns the token. Documented across NextAuth #1840, FusionAuth #629, Ghost forum, Bubble forum, HN.
- **Supabase PKCE specifics:** the code-exchange needs *both* the auth code (from the URL) **and** the code verifier (created+stored locally in the browser that *initiated* the flow). If the link is opened anywhere other than the originating browser/device — or pre-consumed by a scanner — you get **`both auth code and code verifier should be non-empty`** / `otp_expired`. (Supabase PKCE docs + Discussion #35510.)
- **Recommended mitigations (from Supabase + community):**
  1. Prefer **OTP codes** (6-digit, user types them) over click-to-verify links — scanners can't "click" a code. Best practice: 6-digit, **5–10 min expiry, 3–5 attempts, 30–60s resend cooldown**, per-IP + per-email rate limits, invalidate old code on resend, single-use.
  2. If keeping links, make the link **land on a page that asks the user to confirm/enter the code**, rather than the link itself consuming the token (no token spend on GET).
  3. Detect SafeLinks scanner requests (IP ranges / headers / user-agent) and return **200 without consuming** the token.
  4. `rel="noreferrer noopener"` / headers signalling scanners not to follow.

### INFER for NovaCRM (directly ties to the open carry-over task)
- NovaCRM uses **Supabase PKCE email verification** and has an unresolved "PKCE real-email verification" task. The two classic PKCE failure modes — **(a) prefetch/SafeLinks consuming the token** and **(b) cross-browser/device opens missing the local code verifier** — are the most probable root causes. Any B2B prospect on Outlook/Microsoft 365 (i.e. a large share of CRM buyers) will disproportionately hit this.
- **Strong recommendation:** switch the *signup confirmation* path from PKCE click-link to **email OTP code entry** (or a link → "click to confirm" landing page that only spends the token on explicit user action). This both fixes the prefetch bug and removes the cross-device fragility. This is likely a higher-leverage fix than swapping email providers — though it presupposes provider deliverability is already solved (i.e. you're off built-in SMTP).

**Sources:**
- https://supabase.com/docs/guides/troubleshooting/otp-verification-failures-token-has-expired-or-otp_expired-errors-5ee4d0
- https://supabase.com/docs/guides/auth/sessions/pkce-flow
- https://github.com/orgs/supabase/discussions/35510 (PKCE token error after email confirmation expiry)
- https://github.com/nextauthjs/next-auth/issues/1840 (Outlook SafeLinks breaks magic links)
- https://github.com/FusionAuth/fusionauth-issues/issues/629
- https://forum.ghost.org/t/magic-links-don-t-work-when-outlook-safe-links-are-enabled/18033
- https://learn.microsoft.com/en-us/defender-office-365/safe-links-about
- https://medium.com/@minhtamphamtol/how-to-fix-magic-link-authentication-issues-with-outlook-safelinks-78bee42e445c
- https://news.ycombinator.com/item?id=38896861
- https://www.answeroverflow.com/m/1399546296741793822 (Supabase-specific prefetch discussion; WebFetch 403'd but surfaced via search)

---

## 5. Signup-confirmation email best practices (conversion + UX)

### What sources SAY
- **Link expiry by use case** (Suped + Stripo + Mailtrap, converging):
  - Passwordless sign-in (grants a session) → **15–60 min** (short-lived credential).
  - Sensitive account changes (email change, admin invite) → **24h**.
  - **Standard signup verification / double opt-in → 48h default, 72h** when audience checks a work inbox after a weekend.
  - Low-risk address confirmation w/ no account access → up to **7 days**.
  - Practical baseline: **"Set standard email verification links to 48h; extend to 72h only when data shows real users need it."**
- **Don't send from `no-reply@`** — hurts deliverability (more likely to hit spam) and is "faceless." Use a real/branded sender. *(Directly contradicts the common `no-reply@example.com` default Supabase suggests.)*
- **Tell users when the link expires**, and **include a copyable plain-text confirmation link** (not only a button).
- **Expired-link handling:** send users to a dedicated **expired-link page with one action — "request a fresh message"** — not a dead-end error.
- **Resend UX:** clear "Check your inbox to verify your email" state + a **"Resend email"** option + ability to **change the email address**; on code expiry show a **"Resend code"** button. Enforce **30–60s resend cooldown**.
- **Conversion context:** confirmation emails land in the primary inbox and get **high open rates**, so they're prime real estate to nudge activation. (Promotional benchmark for contrast: 1.5–3% typical conversion, 4–6% for well-segmented.) Incomplete *delivery* frequently masquerades as an *expiry* problem — verify SPF/DKIM/DMARC before lengthening token TTLs.

### INFER for NovaCRM
- Quick conversion wins independent of provider choice: (1) branded sender instead of `no-reply@`; (2) confirmation email must include a **copyable link AND** ideally a typed OTP; (3) a proper **expired-link → resend** page; (4) visible **resend button w/ 30–60s cooldown**; (5) set confirmation TTL to **48–72h** (CRM buyers are work-inbox users → lean 72h).
- Because confirmation mail has high open rates, NovaCRM should treat it as the first activation touchpoint (e.g., "confirm → land in demo mode") rather than a bare system message.

**Sources:**
- https://www.suped.com/learn/email-deliverability/how-long-should-an-email-verification-link-remain-active
- https://stripo.email/blog/subscription-confirmation-email-best-practices-examples/
- https://mailtrap.io/blog/confirmation-emails/
- https://getathenic.com/blog/email-marketing-conversion-rate-guide
- https://www.scalekit.com/blog/otp-vs-magic-links-passwordless-authentication
- https://mojoauth.com/blog/sms-otp-vs-magic-links-vs-passkeys-ecommerce-conversion
- https://www.authgear.com/post/login-signup-ux-guide/
- https://supabase.com/docs/guides/auth/auth-email-passwordless

---

## Source count: 30+ distinct URLs across 5 sub-topics (lens minimum was 8). Mix of: official Supabase docs, official Resend docs, AWS docs, Microsoft docs, neutral benchmark (Mailtrap), vendor-biased (Postmark), GitHub issues, community forums, pricing aggregators.

## Bias ledger
- **Postmark comparison page** = competitor marketing; architecture facts corroborated, latency/error numbers self-selected → low-confidence on the specific ms/% figures.
- **Pingram / Dreamlit / Nuntly / Sequenzy** = content-marketing blogs (often selling their own product); used only for corroborating widely-repeated facts (2/hr, 30/hr, free-tier sizes), not as sole source for anything load-bearing.
- **Mailtrap** benchmark also sells email infra but publishes a comparative inbox-placement methodology → treated as the most neutral deliverability figure available, still directional.
- Supabase docs render rate limits as template variables, not literals → concrete "2/hr" and "30/hr" come from secondary corroboration (consistent across many independent sources) + the docs' own structure.
