import type { TourModule } from "../types";

/**
 * Module 0 — "Get set up".
 *
 * This is the content layer only: it fills the engine's six-slot template for
 * each step of first-run setup (signup → name workspace → pick mode → connect
 * Gmail + Slack → invite team) and anchors each step to the REAL onboarding
 * wizard UI (apps/web/src/app/onboarding/page.tsx) via `data-tour` selectors.
 *
 * Anchors for later steps (mode grid, integrations, invite) only mount once the
 * user advances the wizard — the engine polls for them and keeps the popover
 * centered until they appear, so the tour walks alongside the wizard. Every
 * checkpoint is manual-confirm; the soft-verifies here only read the DOM to
 * offer a gentle nudge and never block progress.
 *
 * Voice mirrors the Help page: confident, plain, benefit-first, "you stay in
 * control." No AI tip is used in Module 0 (the slot exists for later modules).
 */

/** DOM soft-check: is an element matching `selector` present? */
const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

/** DOM soft-check: does an element's text contain `text` (case-insensitive)? */
const textPresent = (selector: string, text: string) => () => {
  if (typeof document === "undefined") return false;
  const el = document.querySelector(selector);
  return !!el && (el.textContent ?? "").toLowerCase().includes(text.toLowerCase());
};

export const module0Setup: TourModule = {
  id: "module-0-setup",
  title: "Get set up",
  description:
    "Stand up your workspace and connect your tools so the agents can start working. Takes about two minutes.",
  steps: [
    {
      id: "welcome",
      title: "Welcome to NovaCRM",
      whyThisExists:
        "NovaCRM connects to the tools your team already uses and runs autonomous agents that handle CRM busywork. This quick setup gets your workspace ready so those agents have something to work with.",
      anchor: { selector: '[data-tour="onboarding-card"]', placement: "auto", padding: 6 },
      actionGuidance:
        "Nothing to do yet — just follow along. Each step points at exactly what to fill in, and you can leave the tour anytime with Esc or the ✕.",
      whatJustHappened:
        "You're signed in and looking at the setup wizard. Everything from here lives in your own workspace, isolated per tenant.",
      forwardReference: "Next: give your workspace a name.",
      checkpoint: { confirmLabel: "Let's go → Next" },
    },
    {
      id: "name-workspace",
      title: "Name your workspace",
      whyThisExists:
        "Your workspace is the container for every contact, deal, message, and agent action. The name is how your team will recognize it.",
      prerequisiteCheck: {
        label: "You're on the first step of the wizard.",
        verify: present('[data-tour="workspace-name"]'),
        nudge: "This step lives on the wizard's first screen — if you've moved on, tap Back in the wizard.",
      },
      anchor: { selector: '[data-tour="workspace-name"]', placement: "bottom", padding: 6 },
      actionGuidance:
        "Type a name — your company or team name works well. We'll auto-generate a URL-safe slug from it, shown just below the field.",
      whatJustHappened:
        "Once you continue, NovaCRM has a home for your data. The slug becomes part of your workspace's identity.",
      forwardReference: "Next: choose how your team will use NovaCRM.",
      checkpoint: {
        confirmLabel: "I've named it → Next",
        verify: () => {
          if (typeof document === "undefined") return false;
          const input = document.querySelector<HTMLInputElement>('[data-tour="workspace-name"]');
          return !!input && input.value.trim().length > 0;
        },
        nudge: "The name field still looks empty — add a name in the wizard, then continue. (You can proceed regardless.)",
      },
    },
    {
      id: "pick-mode",
      title: "Choose your mode",
      whyThisExists:
        "Mode tailors the whole app to how you work. Sales unlocks pipeline, leads, campaigns, and outreach; Project Management unlocks tasks and projects; Both gives you the full platform. It also decides which items appear in your sidebar.",
      prerequisiteCheck: {
        label: "You've named your workspace and moved to the mode step.",
        verify: present('[data-tour="mode-select"]'),
        nudge: "Click Continue on the naming step to reach mode selection.",
      },
      anchor: { selector: '[data-tour="mode-select"]', placement: "auto", padding: 6 },
      actionGuidance:
        "Pick the mode that matches your team. Not sure? Both is the safe default — you can change it later in Settings.",
      whatJustHappened:
        "Continuing here creates your workspace on the server with the mode you chose, and refreshes your session so it's bound to the new workspace.",
      forwardReference: "Next: connect Gmail and Slack so the agents have data to act on.",
      checkpoint: {
        confirmLabel: "Mode picked → Next",
      },
    },
    {
      id: "connect-tools",
      title: "Connect Gmail & Slack",
      whyThisExists:
        "This is where NovaCRM earns its keep. Gmail lets it sync email and send AI-drafted replies; Slack imports conversations and powers human-in-the-loop approvals. Connect them and the agents start ingesting right away — no manual data entry.",
      prerequisiteCheck: {
        label: "You're on the integrations step.",
        verify: present('[data-tour="integrations"]'),
        nudge: "Reach this step by continuing past mode selection.",
      },
      anchor: { selector: '[data-tour="integrations"]', placement: "auto", padding: 6 },
      actionGuidance:
        "Click Connect on Gmail and Slack and approve access in the popup. You can connect one, both, or skip for now and add them later from Connectors.",
      whatJustHappened:
        "Connected tools begin feeding contacts, messages, and calls into your workspace. Anything high-stakes — like sending an email — still routes through your approval.",
      forwardReference: "Next: bring your team along.",
      checkpoint: {
        confirmLabel: "Tools handled → Next",
        verify: textPresent('[data-tour="integrations"]', "connected"),
        nudge: "No connection detected yet — that's OK, you can connect Gmail and Slack later from the Connectors page.",
      },
    },
    {
      id: "invite-team",
      title: "Invite your team",
      whyThisExists:
        "NovaCRM is built for teams. Inviting people now means shared context — everyone sees the same contacts, deals, and agent activity from day one.",
      prerequisiteCheck: {
        label: "You're on the invite step.",
        verify: present('[data-tour="invite-team"]'),
        nudge: "Continue past integrations to reach team invites.",
      },
      anchor: { selector: '[data-tour="invite-team"]', placement: "top", padding: 6 },
      actionGuidance:
        "Enter a teammate's email and click Invite. Adding people is optional — you can always invite more later from Settings.",
      whatJustHappened:
        "Invited teammates get access to this workspace. You stay the owner and control what happens next.",
      forwardReference: "Last step: open your workspace.",
      checkpoint: {
        confirmLabel: "Done here → Next",
      },
    },
    {
      id: "launch",
      title: "You're all set",
      whyThisExists:
        "Setup is complete. Your workspace exists, your tools are connected, and the agents are ready to start working the moment you land on the dashboard.",
      prerequisiteCheck: {
        label: "You're on the final wizard screen.",
        verify: present('[data-tour="launch"]'),
      },
      anchor: { selector: '[data-tour="launch"]', placement: "top", padding: 6 },
      actionGuidance:
        "Click Go to Dashboard to enter your workspace. From there, press ⌘K anytime to ask Nova a question about your pipeline.",
      whatJustHappened:
        "That's the whole setup. The agents begin scoring, tagging, and summarizing in the background — you just supervise the parts that matter.",
      forwardReference: "The Help page (in the sidebar) has a full walkthrough whenever you want it.",
      checkpoint: { confirmLabel: "Finish" },
    },
  ],
};
