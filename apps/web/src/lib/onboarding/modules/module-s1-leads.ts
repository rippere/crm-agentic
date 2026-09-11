import type { WorkspaceMode } from "@/lib/types";
import type { TourModule } from "../types";

/**
 * S1 — "Leads" (Sales track; mode = Sales or Both; builds on Module 3).
 *
 * Leads are the top of the sales funnel: capture them, let the AI score them by
 * engagement, and promote the ready ones into contacts/deals. Real data.
 *
 * Anchors (data-tour selectors on /leads):
 *   - [data-tour="leads-new"]   → "New Lead" button
 *   - [data-tour="leads-stats"] → the engagement-scored funnel stat tiles
 *   - [data-tour="leads-list"]  → the leads table (open a lead → Promote)
 *
 * Mode-gating: every step is showForModes ["sales","both"], so a PM workspace
 * filters this module to zero steps and AppTour never offers it there.
 */

const SALES: WorkspaceMode[] = ["sales", "both"];

const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const moduleS1Leads: TourModule = {
  id: "module-s1-leads",
  title: "Leads",
  description:
    "Work the top of your funnel: capture leads, let AI score them, and promote the hot ones into deals.",
  steps: [
    {
      id: "capture-lead",
      title: "Capture a lead",
      showForModes: SALES,
      whyThisExists:
        "Leads are people who aren't customers yet but could be. Getting them into NovaCRM early means the scoring and follow-up agents can start working them before they go cold.",
      prerequisiteCheck: {
        label: "You've finished the shared core and opened Leads.",
        verify: present('[data-tour="leads-new"]'),
        nudge: "Open Leads from the sidebar (Sales workspaces) to follow along.",
      },
      anchor: { selector: '[data-tour="leads-new"]', placement: "left", padding: 6 },
      actionGuidance:
        "Click New Lead and add someone — a name and a source (referral, inbound, event) is enough. You can also Import CSV to bring in a whole list.",
      whatJustHappened:
        "You've started your funnel. New leads land in the earliest stage and are engagement-scored immediately.",
      forwardReference:
        "As a lead warms up you'll promote them into a contact and a deal — the Pipeline you'll see next.",
      checkpoint: { confirmLabel: "Added a lead → Next" },
    },
    {
      id: "lead-scoring",
      title: "Every lead gets scored",
      showForModes: SALES,
      whyThisExists:
        "Not every lead deserves the same attention. NovaCRM scores each one by engagement so you spend your time on the people most likely to convert — no manual triage.",
      prerequisiteCheck: {
        label: "You're on the Leads page.",
        verify: present('[data-tour="leads-stats"]'),
      },
      anchor: { selector: '[data-tour="leads-stats"]', placement: "bottom", padding: 8 },
      actionGuidance:
        "Look at the funnel tiles — leads are grouped by stage, and each carries an engagement score. Click a tile to filter, or switch to the Funnel view to see them as a board.",
      whatJustHappened:
        "Your funnel is now ranked. The score updates as engagement signals come in, so the hottest leads keep rising to the top.",
      forwardReference:
        "These scores are the same signal that feeds deal health once a lead becomes a deal.",
      checkpoint: { confirmLabel: "Makes sense → Next" },
      aiTip: {
        text: "AI tip: lead scoring is a transparent heuristic over engagement, firmographic, and history signals — not a black box. A lead climbing the score is your cue to promote them.",
        prompt: "Explain engagement-based lead scoring and what a rising score signals for next action.",
      },
    },
    {
      id: "promote-lead",
      title: "Promote when they're ready",
      showForModes: SALES,
      whyThisExists:
        "A hot lead should become a real opportunity. Promoting converts a lead into a contact and a deal in one move, so nothing gets re-typed and the relationship carries forward.",
      prerequisiteCheck: {
        label: "You have leads in the list.",
        verify: present('[data-tour="leads-list"]'),
      },
      anchor: { selector: '[data-tour="leads-list"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Open a lead to see its detail panel, then use Promote to turn it into a contact and a deal. The lead's score and history come along automatically.",
      whatJustHappened:
        "You've moved someone from 'maybe' to 'in the pipeline.' They now exist as a contact (Module 2) and a deal you can work.",
      forwardReference:
        "That new deal shows up on your Pipeline board — which is exactly where S2 picks up.",
      checkpoint: { confirmLabel: "Finish" },
    },
  ],
};
