import type { WorkspaceMode } from "@/lib/types";

/**
 * Onboarding tour engine — type model.
 *
 * The engine is content-agnostic: modules (Module 0 "Get set up", and every
 * later module) supply an array of `TourStep`s built from the spec's six-slot
 * template. The engine renders them, tracks progress, and enforces SOFT gating.
 *
 * Six-slot template (spec §, one field per slot):
 *   1. whyThisExists      — one line of motivation, shown first
 *   2. prerequisiteCheck  — optional, soft: what should already be true
 *   3. anchor             — the DOM element to spotlight
 *   4. actionGuidance     — what to actually do
 *   5. whatJustHappened    (+ forwardReference) — payoff + a pointer forward
 *   6. checkpoint         — manual-confirm ("I did it → Next") + optional soft-verify
 * plus an optional AI-tip slot (mechanism only — Module 0 supplies none).
 */

/** Where the popover sits relative to the spotlighted target. */
export type TourPlacement = "top" | "bottom" | "left" | "right" | "auto";

/**
 * Slot 3 — anchor. Target is resolved by a stable CSS selector at render time
 * (elements can mount/unmount as a wizard advances, so lookup is retried).
 * When no target is found the popover renders centered with no cut-out.
 */
export interface TourAnchor {
  /** Stable CSS selector, e.g. `[data-tour="workspace-name"]`. */
  selector: string;
  /** Preferred popover placement; `auto` picks the side with the most room. */
  placement?: TourPlacement;
  /** Extra px of breathing room around the highlighted element. */
  padding?: number;
  /**
   * If true and the target never appears, the step still shows (centered).
   * If false, the engine will keep waiting (used for anchors that only appear
   * once the user performs the prior action). Defaults to true.
   */
  centerIfMissing?: boolean;
}

/**
 * A soft check — NEVER blocks. It returns whether the condition looks satisfied;
 * when it isn't, the engine surfaces `nudge` but still lets the user proceed.
 * Sync or async. Runs in the browser; must tolerate being called repeatedly.
 */
export type SoftVerify = () => boolean | Promise<boolean>;

/** Slot 2 — prerequisite check (soft, non-blocking). */
export interface PrerequisiteCheck {
  /** Short label describing what should already be done. */
  label: string;
  /** Optional soft check. If it resolves false, `nudge` is shown. */
  verify?: SoftVerify;
  /** Shown when `verify` is false — a gentle heads-up, not a wall. */
  nudge?: string;
}

/** Slot 6 — checkpoint. Completion is a user click; verify only softens. */
export interface Checkpoint {
  /** The confirm button label, e.g. "I did it → Next". */
  confirmLabel: string;
  /**
   * Optional soft-verify run when the user clicks confirm. If it resolves
   * false, `nudge` is shown once; a second click always advances. Never blocks.
   */
  verify?: SoftVerify;
  /** Shown when `verify` is false on the first confirm attempt. */
  nudge?: string;
}

/**
 * The AI-tip slot. Module 0 uses none; later modules can supply a prompt the
 * host app turns into a contextual tip. The engine only reserves the slot and
 * renders `text` (or a custom node) when present — it does not itself call an LLM.
 */
export interface AITip {
  /** A short, pre-rendered tip string to show inline. */
  text?: string;
  /** The prompt a module would send to the app's AI to generate a tip. */
  prompt?: string;
}

/** One tour step = one filled six-slot template. */
export interface TourStep {
  /** Stable id, unique within the module (used for progress + completion). */
  id: string;
  /** Card heading. */
  title: string;

  /** Slot 1. */
  whyThisExists: string;
  /** Slot 2 (optional). */
  prerequisiteCheck?: PrerequisiteCheck;
  /** Slot 3. */
  anchor: TourAnchor;
  /** Slot 4. */
  actionGuidance: string;
  /** Slot 5. */
  whatJustHappened: string;
  /** Slot 5 companion — a pointer to what this unlocks next. */
  forwardReference?: string;
  /** Slot 6. */
  checkpoint: Checkpoint;
  /** Optional AI-tip slot. */
  aiTip?: AITip;

  /**
   * Mode-branch (spec §2). If set, the step is shown ONLY for these workspace
   * modes. If `hideForModes` is set, the step is hidden for those modes. A step
   * whose anchor targets nav the current mode hides MUST declare that here so
   * the engine never spotlights a hidden element.
   */
  showForModes?: WorkspaceMode[];
  hideForModes?: WorkspaceMode[];
}

/** A module = an ordered set of steps with a title. */
export interface TourModule {
  /** Stable id, e.g. "module-0-setup". */
  id: string;
  /** Human title, e.g. "Get set up". */
  title: string;
  /** One-line description of the module. */
  description: string;
  /** Ordered steps (pre-mode-filter). */
  steps: TourStep[];
}

/** Persisted per-user/workspace progress for one module. */
export interface TourProgress {
  moduleId: string;
  /** Index into the mode-filtered step list. */
  stepIndex: number;
  /** Ids of steps the user has confirmed complete. */
  completedStepIds: string[];
  status: "not-started" | "in-progress" | "completed" | "skipped";
  /** ISO timestamp of the last update. */
  updatedAt: string;
}

/** Runtime status of a soft-verify for the current step. */
export type VerifyState = "idle" | "checking" | "ok" | "failed";
