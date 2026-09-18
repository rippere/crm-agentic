import type { WorkspaceMode } from "@/lib/types";
import type { TourModule } from "../types";

/**
 * P1 — "Tasks" (PM track; mode = PM or Both; builds on Module 3).
 *
 * The task board: capture work, organize it by status, and let the AI
 * prioritize. Ties back to the tasks auto-extracted from the inbox and calls in
 * Module 3.
 *
 * Anchors (data-tour selectors on /tasks):
 *   - [data-tour="tasks-new"]        → "New Task" button
 *   - [data-tour="tasks-board"]      → the status board (Open / In Progress / Done)
 *   - [data-tour="tasks-prioritize"] → the "AI Prioritize" button
 *
 * Mode-gating: every step is showForModes ["pm","both"], so a Sales workspace
 * filters this module to zero steps and AppTour never offers it there.
 */

const PM: WorkspaceMode[] = ["pm", "both"];

const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const moduleP1Tasks: TourModule = {
  id: "module-p1-tasks",
  title: "Tasks",
  description:
    "Capture work, organize it by status on a board, and let AI decide what to do first.",
  steps: [
    {
      id: "capture-task",
      title: "Capture a task",
      showForModes: PM,
      whyThisExists:
        "Work you can see is work that gets done. Tasks are the atomic unit of your PM workspace — and many of them arrive on their own, extracted from the messages and calls you connected in Module 3.",
      prerequisiteCheck: {
        label: "You've finished the shared core and opened Tasks.",
        verify: present('[data-tour="tasks-new"]'),
        nudge: "Open Tasks from the sidebar (PM workspaces) to follow along.",
      },
      anchor: { selector: '[data-tour="tasks-new"]', placement: "left", padding: 6 },
      actionGuidance:
        "Click New Task and add something real you need to do. Give it a due date if you have one — the AI uses it when prioritizing.",
      whatJustHappened:
        "You've added to your board. Tasks auto-extracted from inbox triage and call summaries land here too, so nothing falls through.",
      forwardReference:
        "Tasks group under Projects, which you'll organize in P2.",
      checkpoint: { confirmLabel: "Added a task → Next" },
    },
    {
      id: "task-board",
      title: "Organize by status",
      showForModes: PM,
      whyThisExists:
        "A board makes your workload legible at a glance: what's open, what's in progress, and what's done. Dragging a card is all it takes to move work forward.",
      prerequisiteCheck: {
        label: "You're on the Tasks page.",
        verify: present('[data-tour="tasks-board"]'),
      },
      anchor: { selector: '[data-tour="tasks-board"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Drag a task from Open to In Progress to Done as you work it. Use the filters up top to focus on a single status.",
      whatJustHappened:
        "Your work is now visible and moving. Status is just a drag — no forms, no updates to write.",
      forwardReference:
        "When the list gets long, let the AI decide the order — that's the next step.",
      checkpoint: { confirmLabel: "Got it → Next" },
    },
    {
      id: "ai-prioritize",
      title: "Let AI prioritize",
      showForModes: PM,
      whyThisExists:
        "When everything feels urgent, deciding what to do first is its own work. NovaCRM ranks your open tasks by importance and deadline so you can just start at the top.",
      prerequisiteCheck: {
        label: "The AI Prioritize control is in your toolbar.",
        verify: present('[data-tour="tasks-prioritize"]'),
      },
      anchor: { selector: '[data-tour="tasks-prioritize"]', placement: "bottom", padding: 6 },
      actionGuidance:
        "Click AI Prioritize. NovaCRM analyzes your open tasks — due dates, clarity, and importance — and orders them so the highest-impact work rises to the top.",
      whatJustHappened:
        "Your board is now sorted by what matters most. You've got a task capture → organize → prioritize loop that runs itself.",
      forwardReference:
        "Group related tasks into Projects next (P2) to see the bigger picture and get a project-level health check.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: task prioritization uses Claude to weigh deadlines, importance, and clarity across your open tasks — a ranked to-do list you can trust, refreshed whenever you ask.",
        prompt: "Explain AI task prioritization: how it ranks open tasks by deadline, importance, and clarity.",
      },
    },
  ],
};
