import type { WorkspaceMode } from "@/lib/types";
import type { TourModule } from "../types";

/**
 * S3 — "Sequences → Campaigns → Outreach" (Sales track; Sales or Both; builds on S2).
 *
 * Automating follow-up, end to end: build a reusable sequence, launch it as a
 * campaign against a segment, and approve the AI-drafted messages in the
 * outreach queue (bot drafts → human approves). Spans three pages; the steps
 * guide the user across them and the spotlight re-attaches as they navigate.
 *
 * Anchors (data-tour selectors):
 *   - [data-tour="sequences-new"]  → "New Sequence" (/sequences)
 *   - [data-tour="campaigns-new"]  → "New Campaign" (/campaigns)
 *   - [data-tour="outreach-queue"] → the approval queue (/outreach)
 *
 * Mode-gating: every step is showForModes ["sales","both"].
 */

const SALES: WorkspaceMode[] = ["sales", "both"];

const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const moduleS3Outreach: TourModule = {
  id: "module-s3-outreach",
  title: "Sequences, Campaigns & Outreach",
  description:
    "Automate follow-up: a reusable sequence, a targeted campaign, and AI-drafted messages you approve.",
  steps: [
    {
      id: "build-sequence",
      title: "Build a follow-up sequence",
      showForModes: SALES,
      whyThisExists:
        "Consistent follow-up wins deals, but doing it by hand doesn't scale. A sequence is a reusable, multi-step drip recipe — write it once and reuse it for every prospect who fits.",
      prerequisiteCheck: {
        label: "You've worked your pipeline and opened Sequences.",
        verify: present('[data-tour="sequences-new"]'),
        nudge: "Open Sequences from the sidebar (Sales workspaces) to follow along.",
      },
      anchor: { selector: '[data-tour="sequences-new"]', placement: "left", padding: 6 },
      actionGuidance:
        "Click New Sequence and sketch a few steps — intro, value, a nudge. Think of it as the template; you'll aim it at people in the next step.",
      whatJustHappened:
        "You've created a reusable play. Any number of contacts can be enrolled in it without rewriting a thing.",
      forwardReference:
        "Next you'll point this sequence at a segment of people — that's a Campaign.",
      checkpoint: { confirmLabel: "Built one → Next" },
    },
    {
      id: "launch-campaign",
      title: "Launch a campaign",
      showForModes: SALES,
      whyThisExists:
        "A campaign is how a sequence meets an audience: segment → sequence → send. It enrolls the right people and runs the follow-up for you, at scale.",
      prerequisiteCheck: {
        label: "Open Campaigns from the sidebar to reach this step.",
        verify: present('[data-tour="campaigns-new"]'),
        nudge: "Head to Campaigns in the sidebar — the popover will follow you there.",
      },
      anchor: { selector: '[data-tour="campaigns-new"]', placement: "left", padding: 6 },
      actionGuidance:
        "Click New Campaign, choose a segment of contacts, and attach the sequence you just built. NovaCRM enrolls them and starts the follow-up.",
      whatJustHappened:
        "Your follow-up is now running on autopilot for a whole segment — enrolled, sent, and tracked (enrolled / sent / replied).",
      forwardReference:
        "Before anything actually sends on your behalf, the AI-drafted messages wait for your sign-off — that's Outreach.",
      checkpoint: { confirmLabel: "Launched / got it → Next" },
    },
    {
      id: "approve-outreach",
      title: "Approve the AI drafts",
      showForModes: SALES,
      whyThisExists:
        "Automation shouldn't mean losing control of your voice. NovaCRM drafts each message with AI, then holds it in an approval queue — bot drafts, you approve. Nothing goes out without a human.",
      prerequisiteCheck: {
        label: "Open Outreach from the sidebar to reach this step.",
        verify: present('[data-tour="outreach-queue"]'),
        nudge: "Head to Outreach in the sidebar to see the approval queue (it's empty until a campaign drafts something).",
      },
      anchor: { selector: '[data-tour="outreach-queue"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Review a queued draft. Edit it, hit Regenerate for a fresh AI take, or Approve to send. Each draft is personalized to the contact and where they are in the sequence.",
      whatJustHappened:
        "You've closed the loop: sequences and campaigns automate the busywork, AI writes the first draft, and you stay the final word on anything that leaves the building.",
      forwardReference:
        "Replies flow back onto the contact and the deal — and the results of all this show up in your Reports dashboards, which is S4.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: reply drafting uses Claude to write context-aware messages grounded in the contact and deal stage; sequences decide the timing and steps. You approve every send — the AI never sends on its own.",
        prompt: "Explain AI reply drafting and automated follow-up sequences, emphasizing human approval before send.",
      },
    },
  ],
};
