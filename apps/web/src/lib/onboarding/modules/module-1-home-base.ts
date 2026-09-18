import type { TourModule } from "../types";

/**
 * Module 1 — "Your home base" (shared core; runs for every workspace mode).
 *
 * Builds directly on Module 0: it assumes the workspace exists and the user has
 * landed in the app shell. It teaches the three things every NovaCRM session
 * runs through — the dashboard, the left sidebar, and the ⌘K command bar — and
 * introduces the product's AI, Nova, IN CONTEXT on the ⌘K step (the first module
 * to use the engine's AI-tip slot), never bolted on.
 *
 * Anchors are real post-login shell elements (added as `data-tour` selectors):
 *   - [data-tour="dashboard-home"]  → the dashboard KPI section
 *   - [data-tour="sidebar"]         → the whole sidebar <aside> (see mode note)
 *   - [data-tour="cmdk-trigger"]    → the sidebar search / ⌘K button
 *   - [data-tour="cmdk-nova"]       → the palette's "Nova AI" tab (only mounted
 *                                     while the palette is open; centers if absent)
 *
 * Mode-awareness (spec §2 branch-by-mode): the sidebar shows different nav per
 * mode (Sales/PM/Both). This module NEVER spotlights an individual nav item —
 * the sidebar step highlights the whole <aside> shell and explains that the nav
 * adapts to the chosen mode. So no step can ever highlight a mode-hidden item,
 * and the module needs no showForModes/hideForModes gating. Voice mirrors the
 * Help page: confident, plain, benefit-first.
 */

/** DOM soft-check: is an element matching `selector` present? */
const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const module1HomeBase: TourModule = {
  id: "module-1-home-base",
  title: "Your home base",
  description:
    "Get oriented in the app: the dashboard, the sidebar, and the ⌘K command bar where you'll meet Nova.",
  steps: [
    {
      id: "dashboard",
      title: "This is your dashboard",
      whyThisExists:
        "The dashboard is your home base — a live overview of your book of business. KPIs, recent agent activity, and anything that needs attention surface here first, so you always start the day with the real picture.",
      prerequisiteCheck: {
        label: "You've finished setup and landed in your workspace.",
        verify: present('[data-tour="sidebar"]'),
        nudge: "This module runs inside the app. If you haven't finished setup yet, complete Module 0 first — you can still look around.",
      },
      anchor: { selector: '[data-tour="dashboard-home"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Take a look at your KPI row. It's empty-ish for now — that's expected on a brand-new workspace. It fills in automatically as you add contacts and deals and the agents get to work.",
      whatJustHappened:
        "You're looking at the same dashboard you'll return to every session. Nothing here is a demo — it reflects your real workspace.",
      forwardReference:
        "These numbers come alive once you add your first contacts (Module 2) and deals — you'll watch them populate.",
      checkpoint: { confirmLabel: "Got it → Next" },
    },
    {
      id: "sidebar",
      title: "Navigate from the sidebar",
      whyThisExists:
        "The left sidebar is how you move around NovaCRM — every feature lives here, grouped into Workspace, Intelligence, and System. It adapts to the mode you picked: Sales, Project Management, or Both, so you only see what's relevant to how you work.",
      prerequisiteCheck: {
        label: "You're in the app shell.",
        verify: present('[data-tour="sidebar"]'),
      },
      anchor: { selector: '[data-tour="sidebar"]', placement: "right", padding: 4 },
      actionGuidance:
        "Hover over the rail on the left to expand it and see the labels. The items you see match your workspace mode — a Sales workspace shows Pipeline and Leads, a PM workspace shows Tasks and Projects. You can change mode anytime in Settings.",
      whatJustHappened:
        "That's your whole map. Because the nav is mode-aware, you'll never wade through features you don't use.",
      forwardReference:
        "Each nav item is a module coming up — Contacts, Inbox & Calls, and your mode's track (Pipeline for Sales, Projects for PM).",
      checkpoint: { confirmLabel: "Makes sense → Next" },
    },
    {
      id: "command-bar",
      title: "The ⌘K command bar",
      whyThisExists:
        "⌘K is the fastest way to get anywhere and find anything. One shortcut opens a command bar that searches across every contact, deal, and task in your workspace — no clicking through pages.",
      prerequisiteCheck: {
        label: "The ⌘K trigger is in your sidebar.",
        verify: present('[data-tour="cmdk-trigger"]'),
      },
      anchor: { selector: '[data-tour="cmdk-trigger"]', placement: "right", padding: 6 },
      actionGuidance:
        "Press ⌘K (Ctrl+K on Windows) now, or click this Search button. Try typing a couple of letters — results group by contacts, deals, and tasks as you type.",
      whatJustHappened:
        "You just opened your universal search. It's always a keystroke away from any page in the app.",
      forwardReference:
        "The same command bar has a second mode — Nova AI — which is up next.",
      checkpoint: {
        confirmLabel: "Opened it → Next",
        verify: present('[data-tour="cmdk-palette"]'),
        nudge: "Didn't catch the palette open — no problem, press ⌘K whenever you like. Continuing.",
      },
    },
    {
      id: "meet-nova",
      title: "Meet Nova",
      whyThisExists:
        "Nova is NovaCRM's built-in AI — ask your CRM anything in plain language and get an answer with full context across your pipeline. It's the same intelligence that powers the agents, available to you on demand.",
      prerequisiteCheck: {
        label: "You know how to open ⌘K.",
        verify: present('[data-tour="cmdk-trigger"]'),
      },
      // Anchors the palette's "Nova AI" tab when the palette is open; centers
      // otherwise (the tab only mounts while ⌘K is open). Either way the tip below
      // introduces Nova in context — this is the AI woven into the module it helps.
      anchor: { selector: '[data-tour="cmdk-nova"]', placement: "bottom", padding: 6, centerIfMissing: true },
      actionGuidance:
        "In the ⌘K bar, switch to the Nova AI tab and ask something like \"What's stale in my pipeline?\" or \"Draft a follow-up for Acme.\" Nova answers from your live data — and holds high-stakes actions, like sending an email, for your approval.",
      whatJustHappened:
        "You've met the AI layer. Nova reads your workspace, never trains on your data, and always keeps you in control of anything that leaves the building.",
      forwardReference:
        "From here every module introduces the AI that fits it — contact enrichment, lead scoring, call summaries — but Nova via ⌘K is always the front door.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "Nova tip: press ⌘K, hit the Nova AI tab, and ask in plain English — \"Who are my hottest leads this week?\" There are starter chips in the bar if you're not sure where to begin.",
        prompt: "Introduce Nova as the in-app AI available via ⌘K; give one concrete example query grounded in the user's workspace.",
      },
    },
  ],
};
