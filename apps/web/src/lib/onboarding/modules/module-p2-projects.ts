import type { WorkspaceMode } from "@/lib/types";
import type { TourModule } from "../types";

/**
 * P2 — "Projects" (PM track; mode = PM or Both; builds on P1).
 *
 * Projects group tasks into larger bodies of work, and the PM agent gives each
 * one a health check. Projects can also be auto-extracted from Gmail
 * conversations.
 *
 * Anchors (data-tour selectors on /projects):
 *   - [data-tour="projects-new"]  → "New Project" button
 *   - [data-tour="projects-list"] → the project cards grid (manual + auto)
 *
 * Mode-gating: every step is showForModes ["pm","both"].
 */

const PM: WorkspaceMode[] = ["pm", "both"];

const present = (selector: string) => () =>
  typeof document !== "undefined" && document.querySelector(selector) !== null;

export const moduleP2Projects: TourModule = {
  id: "module-p2-projects",
  title: "Projects",
  description:
    "Group work into projects and get an AI health check on each one.",
  steps: [
    {
      id: "create-project",
      title: "Group work into a project",
      showForModes: PM,
      whyThisExists:
        "Tasks are the trees; projects are the forest. A project bundles related tasks into one body of work so you can track progress at the level decisions actually get made.",
      prerequisiteCheck: {
        label: "You've organized your tasks and opened Projects.",
        verify: present('[data-tour="projects-new"]'),
        nudge: "Open Projects from the sidebar (PM workspaces) to follow along.",
      },
      anchor: { selector: '[data-tour="projects-new"]', placement: "left", padding: 6 },
      actionGuidance:
        "Click New Project and name a real initiative — \"Q3 Enterprise Expansion,\" say. You can also let NovaCRM extract projects from your Gmail conversations automatically.",
      whatJustHappened:
        "You've created a container for related work. Tasks from P1 can roll up here, giving each initiative its own home.",
      forwardReference:
        "With a project in place, the PM agent can assess how it's actually tracking — the next step.",
      checkpoint: { confirmLabel: "Created one → Next" },
    },
    {
      id: "project-health",
      title: "AI checks project health",
      showForModes: PM,
      whyThisExists:
        "It's easy for a project to drift without anyone noticing. The PM agent reads each project's tasks and activity and gives it a health check, so problems surface while you can still act on them.",
      prerequisiteCheck: {
        label: "Your projects are listed.",
        verify: present('[data-tour="projects-list"]'),
      },
      anchor: { selector: '[data-tour="projects-list"]', placement: "auto", padding: 8 },
      actionGuidance:
        "Open a project to see its detail and the AI health read — progress, momentum, and anything at risk. Manually created and auto-extracted projects both appear here.",
      whatJustHappened:
        "You've completed the PM track. Capture tasks, organize them on a board, prioritize with AI, group them into projects, and get an AI health check — your work now runs on real data.",
      forwardReference:
        "For anything ad hoc, Nova via ⌘K (from Module 1) answers questions across your tasks and projects on demand.",
      checkpoint: { confirmLabel: "Finish" },
      aiTip: {
        text: "AI tip: the project health check uses Claude to assess progress, momentum, and risk from a project's tasks and activity — a project-level status you don't have to assemble by hand.",
        prompt: "Explain the AI project health check: how it assesses progress and risk from a project's tasks and activity.",
      },
    },
  ],
};
