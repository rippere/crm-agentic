import type { TourModule } from "../types";

/**
 * C2 — "Nova AI, deep" (Level-2 capstone; all modes; unlocked later).
 *
 * The depth pass on Nova, the ⌘K assistant introduced in Module 1. Module 1 said
 * "here's Nova, ask your CRM anything"; C2 assumes the user now has real data and
 * goes deep: multi-turn natural-language querying, and scheduled digests /
 * briefings. Surfaced deliberately, never auto-offered on first run.
 *
 * Anchors (the real ⌘K surface, reused from Module 1):
 *   - [data-tour="cmdk-trigger"] → the sidebar ⌘K trigger (always present)
 *   - [data-tour="cmdk-nova"]    → the palette's "Nova AI" tab (present when ⌘K is open)
 *
 * All modes — Nova is shared across the whole product.
 */

const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const moduleC2NovaDeep: TourModule = {
  id: "module-c2-nova-deep",
  title: "Nova AI, deep",
  description:
    "Take the ⌘K assistant from Module 1 to full power: real questions over your real data, plus digests and briefings.",
  steps: [
    {
      id: "nova-full-power",
      title: "Nova, at full power",
      whyThisExists:
        "Back in Module 1 you met Nova and learned to open it with ⌘K. Now that your workspace is full of contacts, deals, messages, and calls, Nova has something to reason over — so this is where it earns its keep.",
      prerequisiteCheck: {
        label: "You met Nova in Module 1 and have data in your workspace.",
        verify: present('[data-tour="cmdk-trigger"]'),
        nudge: "Nova lives behind ⌘K (the Search button in the sidebar) — the same one from Module 1.",
      },
      anchor: { selector: '[data-tour="cmdk-trigger"]', placement: "right", padding: 6 },
      actionGuidance:
        "Open ⌘K, switch to Nova AI, and ask a real question about your book — \"which deals are most at risk and why?\" Then follow up: \"draft outreach for the top one.\" Nova holds context across the turns.",
      whatJustHappened:
        "You just had a conversation with your CRM. This is the difference from Module 1's intro — with real data, Nova reasons across everything you've built, not a demo.",
      forwardReference:
        "Beyond questions you ask, Nova can push answers to you on a schedule — digests and briefings, next.",
      checkpoint: {
        confirmLabel: "Asked Nova → Next",
        verify: present('[data-tour="cmdk-palette"]'),
        nudge: "Didn't catch the palette open — press ⌘K whenever you like. Continuing.",
      },
      aiTip: {
        text: "AI tip: Nova (Claude) answers over your live workspace with full context, and holds it across follow-ups — so you can drill in (\"why?\", \"now draft it\") instead of re-asking. High-stakes actions still route to you for approval.",
        prompt: "Explain deep, multi-turn natural-language querying with Nova over the user's live CRM data.",
      },
    },
    {
      id: "digests-briefings",
      title: "Digests & briefings",
      whyThisExists:
        "The best assistant tells you what matters before you ask. Nova can assemble digests and pre-meeting briefings from your workspace, so you walk in informed without running a single query.",
      prerequisiteCheck: {
        label: "You know how to reach Nova via ⌘K.",
        verify: present('[data-tour="cmdk-trigger"]'),
      },
      anchor: { selector: '[data-tour="cmdk-nova"]', placement: "bottom", padding: 6, centerIfMissing: true },
      actionGuidance:
        "Ask Nova for a briefing — \"give me a morning digest of what changed\" or \"brief me before my call with Acme.\" It pulls the relevant deals, messages, and history into one summary.",
      whatJustHappened:
        "You've taken Nova from a question box to a briefing engine. Digests and briefings turn your whole workspace into a report you can request in plain English.",
      forwardReference:
        "Nova answers on demand; the Nexus agents work in the background without being asked — that's the last capstone module, C3.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: ask Nova for digests (\"what changed since yesterday?\") and pre-meeting briefings (\"brief me on <contact>\") — it composes them from your live data on request, the deep end of the ⌘K assistant you met in Module 1.",
        prompt: "Explain Nova digests and pre-meeting briefings assembled from the user's live workspace.",
      },
    },
  ],
};
