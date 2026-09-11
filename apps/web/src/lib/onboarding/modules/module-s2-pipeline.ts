import type { WorkspaceMode } from "@/lib/types";
import type { TourModule } from "../types";

/**
 * S2 — "Pipeline & Deals" (Sales track; mode = Sales or Both; builds on S1).
 *
 * The Kanban pipeline is where deals live and move. This module teaches the
 * board and stages, deal health, and the AI that coaches the pipeline
 * (Pulse/Narrative + per-deal coaching, forecast, win/loss).
 *
 * Anchors (data-tour selectors on /pipeline):
 *   - [data-tour="pipeline-board"] → the Kanban board (stages + drag)
 *   - [data-tour="pipeline-new"]   → "New Deal" button
 *   - [data-tour="pipeline-pulse"] → the AI "Pipeline Pulse" card
 *
 * Mode-gating: every step is showForModes ["sales","both"].
 */

const SALES: WorkspaceMode[] = ["sales", "both"];

const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const moduleS2Pipeline: TourModule = {
  id: "module-s2-pipeline",
  title: "Pipeline & Deals",
  description:
    "Run your deals on a Kanban board with AI-scored health, coaching, and forecasts.",
  steps: [
    {
      id: "deal-board",
      title: "Your deal board",
      showForModes: SALES,
      whyThisExists:
        "Every deal is a card, every stage a column. The board gives you the whole pipeline at a glance — what's moving, what's stuck, and what's worth the most — so you always know where to push.",
      prerequisiteCheck: {
        label: "You've promoted a lead and opened Pipeline.",
        verify: present('[data-tour="pipeline-board"]'),
        nudge: "Open Pipeline from the sidebar (Sales workspaces) to follow along.",
      },
      anchor: { selector: '[data-tour="pipeline-board"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Scan the columns, then drag a deal from one stage to the next. Each card shows a health score (green/amber/red) so at-risk deals stand out immediately.",
      whatJustHappened:
        "You just moved a deal through your process. Stage changes and health are tracked automatically — no separate status updates.",
      forwardReference:
        "The velocity and conversion of these stage moves is exactly what your Reports dashboards (S4) chart.",
      checkpoint: { confirmLabel: "Got it → Next" },
    },
    {
      id: "add-deal",
      title: "Add a deal",
      showForModes: SALES,
      whyThisExists:
        "Not every deal starts life as a lead. Add one directly when an opportunity comes in another way — a referral, an existing customer expansion — so your pipeline is complete.",
      prerequisiteCheck: {
        label: "You're on the Pipeline board.",
        verify: present('[data-tour="pipeline-new"]'),
      },
      anchor: { selector: '[data-tour="pipeline-new"]', placement: "left", padding: 6 },
      actionGuidance:
        "Click New Deal, give it a title, value, and stage, and link the contact. It appears on the board with an AI-predicted health score.",
      whatJustHappened:
        "Your pipeline reflects real, weighted value now. Every deal you add sharpens the forecast.",
      forwardReference:
        "The more complete your board, the more useful the AI coaching in the next step.",
      checkpoint: { confirmLabel: "Added / got it → Next" },
    },
    {
      id: "pipeline-ai",
      title: "AI coaches your pipeline",
      showForModes: SALES,
      whyThisExists:
        "A board tells you where deals are; the AI tells you what to do about them. Pipeline Pulse and per-deal coaching read your whole pipeline and surface the risks, the forecast, and the next best move.",
      prerequisiteCheck: {
        label: "The Pipeline Pulse card is on the page.",
        verify: present('[data-tour="pipeline-pulse"]'),
      },
      anchor: { selector: '[data-tour="pipeline-pulse"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Read the Pulse insight up top — it flags at-risk deals and average health. Open any deal to get AI coaching: what's stalling it, its win probability, and a recommended next step.",
      whatJustHappened:
        "You've met the deal AI: pipeline pulse, forecast, and per-deal coaching. It turns a static board into a running commentary on your quarter.",
      forwardReference:
        "Coaching often ends in an action — a follow-up email or sequence — which is the automation you'll set up in S3.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: Pipeline Pulse and the Narrative summarize health, momentum, and risk across all deals; open a single deal for coaching, a win/loss read, and a forecast. All grounded in your data, via Claude.",
        prompt: "Explain pipeline pulse/narrative and per-deal coaching, forecast, and win/loss — all grounded in the user's deals.",
      },
    },
  ],
};
