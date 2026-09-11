import type { TourModule } from "../types";

/**
 * C1 — "Goals: Commitments & KPIs" (Level-2 capstone; all modes; unlocked later).
 *
 * Capstone modules assume the user has run the core, has real data, and has
 * built habits — so this is surfaced deliberately (see capstoneModules in
 * modules/index.ts), never auto-offered on first run. C1 teaches setting targets
 * against real activity: KPI trends and commitments scored kept/broken by the
 * weekly retro agent.
 *
 * Anchors (data-tour selectors on /life, the accountability ledger):
 *   - [data-tour="life-kpis"]        → the KPI trend section
 *   - [data-tour="life-commitments"] → the commitments table
 *
 * Surface note: the accountability ledger is owner-private (allowlist-gated), so
 * the soft prerequisiteCheck nudges and the popover centers when it isn't
 * available — the module never spotlights a surface the workspace hides.
 */

const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const moduleC1Goals: TourModule = {
  id: "module-c1-goals",
  title: "Goals: Commitments & KPIs",
  description:
    "Set targets against your real activity and let NovaCRM score how you're tracking.",
  steps: [
    {
      id: "kpi-trends",
      title: "Track your KPIs",
      whyThisExists:
        "Habits stick when you can see them. KPI trends turn your day-to-day activity into a moving picture of how you're doing over weeks — so progress (or drift) is obvious, not a surprise at quarter-end.",
      prerequisiteCheck: {
        label: "You've been using NovaCRM and opened the accountability ledger.",
        verify: present('[data-tour="life-kpis"]'),
        nudge: "This is the Life ledger — it's available on enabled workspaces once the daily collector has pushed KPI snapshots.",
      },
      anchor: { selector: '[data-tour="life-kpis"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Look over the KPI trend cards. Each tracks one metric over a rolling window, scored against your live data — no manual entry, the collector pushes snapshots daily.",
      whatJustHappened:
        "You're seeing your own numbers trend over time. These are the same signals the agents act on, now framed as goals you can watch.",
      forwardReference:
        "KPIs show the trend; commitments make it personal — that's next.",
      checkpoint: { confirmLabel: "Got it → Next" },
    },
    {
      id: "commitments",
      title: "Set commitments and get scored",
      whyThisExists:
        "A commitment is a promise to yourself with a deadline. NovaCRM tracks each one and the weekly retro agent scores it kept or broken against what actually happened — accountability without the spreadsheet.",
      prerequisiteCheck: {
        label: "The commitments table is on the page.",
        verify: present('[data-tour="life-commitments"]'),
      },
      anchor: { selector: '[data-tour="life-commitments"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Add a commitment — something concrete you'll do this week. At week's end the retro agent judges it against your real activity and rolls the result into your kept-rate trend.",
      whatJustHappened:
        "You've turned an intention into something the system tracks and grades. Your kept-rate becomes one more KPI you can improve.",
      forwardReference:
        "For a spoken-word status on any of this, Nova at full power (C2) can pull it together on demand.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: the weekly retro agent reads your git, CRM, and activity to score commitments kept vs broken — an honest, evidence-based review you don't have to write. Kept-rate then trends alongside your KPIs.",
        prompt: "Explain how the weekly retro agent scores commitments kept/broken against real activity evidence.",
      },
    },
  ],
};
