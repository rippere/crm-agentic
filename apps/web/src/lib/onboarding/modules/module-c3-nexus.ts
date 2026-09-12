import type { TourModule } from "../types";

/**
 * C3 — "Nexus agents & Slack approvals" (Level-2 capstone; all modes; unlocked later).
 *
 * The background automation layer and its human-in-the-loop guardrail. Teaches
 * the live Nexus agent-status panel, the agent roster, and the Slack HITL
 * approval flow that gates every high-stakes action. Surfaced deliberately,
 * never auto-offered on first run.
 *
 * Anchors (real, mode-agnostic surfaces):
 *   - [data-tour="nexus-panel"] → the live Nexus agent-status panel (sidebar)
 *   - [data-tour="agents-grid"] → the agent roster (/agents)
 *
 * All modes — Nexus and HITL approvals span the whole product. The approval step
 * anchors the always-present agent roster and explains the Slack flow, rather
 * than a mode-bound queue, so it never spotlights a surface a mode hides.
 */

const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const moduleC3Nexus: TourModule = {
  id: "module-c3-nexus",
  title: "Nexus agents & Slack approvals",
  description:
    "The background automation layer — live agent status, the agent roster, and human-in-the-loop approvals in Slack.",
  steps: [
    {
      id: "meet-nexus",
      title: "Meet Nexus",
      whyThisExists:
        "Everything you've done so far — scoring, tagging, drafting, summarizing — has been agents working in the background. Nexus is the live status panel that shows them running, so the automation is never a black box.",
      prerequisiteCheck: {
        label: "You've used NovaCRM enough to have agents running.",
        verify: present('[data-tour="nexus-panel"]'),
        nudge: "Hover the sidebar to expand it — the Nexus panel sits near the bottom.",
      },
      anchor: { selector: '[data-tour="nexus-panel"]', placement: "right", padding: 6 },
      actionGuidance:
        "Find the Nexus panel at the bottom of the sidebar. It shows which agents are active, processing, or idle in real time — the pulse of your workspace.",
      whatJustHappened:
        "You've seen the automation that's been running all along, made visible. Nexus is how you keep an eye on the agents without micromanaging them.",
      forwardReference:
        "To see what each agent does and run one yourself, open the Agents page — next.",
      checkpoint: { confirmLabel: "Got it → Next" },
    },
    {
      id: "agent-roster",
      title: "Your agent roster",
      whyThisExists:
        "Each agent is a specialist — lead scorer, email composer, call summarizer, deal risk flagger. The Agents page is where you see what each one does, how accurate it is, and run it on demand.",
      prerequisiteCheck: {
        label: "Open Agents from the sidebar to reach this step.",
        verify: present('[data-tour="agents-grid"]'),
        nudge: "Head to Agents in the sidebar (Intelligence group) — the popover will follow you there.",
      },
      anchor: { selector: '[data-tour="agents-grid"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Browse the roster. Each card shows the agent's job, recent run outcomes, and accuracy — hit Run to trigger one and watch it work.",
      whatJustHappened:
        "You now know your workforce. These agents run on schedules and on events, and you can invoke any of them yourself from here.",
      forwardReference:
        "Agents handle the busywork on their own — but anything high-stakes stops for your approval, which is the final step.",
      checkpoint: { confirmLabel: "Makes sense → Next" },
    },
    {
      id: "slack-approvals",
      title: "You approve the high-stakes moves",
      whyThisExists:
        "Autonomy without a guardrail is a liability. NovaCRM lets agents act on the safe stuff, but holds anything high-stakes — sending an email, a big status change — for a human. That approval happens where your team already is: Slack.",
      prerequisiteCheck: {
        label: "You're looking at the agents that do the work.",
        verify: present('[data-tour="agents-grid"]'),
      },
      anchor: { selector: '[data-tour="agents-grid"]', placement: "auto", padding: 8 },
      actionGuidance:
        "When an agent proposes a high-stakes action, it posts to Slack for a one-click approve or dismiss (Gmail/Slack were connected back in Module 0). Approve and it proceeds; dismiss and it doesn't. You're always the final word.",
      whatJustHappened:
        "You've completed the whole product. Agents run in the background, Nexus shows their status, and human-in-the-loop approvals in Slack keep you in control of anything that matters.",
      forwardReference:
        "That's the full tour — from setup to a workspace that runs itself, with you supervising the parts that count. Nova (⌘K) and the Help page are always there when you need them.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: high-stakes agent actions route through human-in-the-loop approval in Slack — approve or dismiss with one click. Agents never send on their own; the AI drafts and proposes, you decide.",
        prompt: "Explain the Slack human-in-the-loop approval flow for high-stakes agent actions.",
      },
    },
  ],
};
