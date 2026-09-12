"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { WorkspaceMode } from "@/lib/types";
import type { TourModule, TourProgress, TourStep } from "./types";

/* ─── Persistence ─── */

const STORAGE_PREFIX = "novacrm.tour";

function storageKey(moduleId: string, scopeKey: string): string {
  return `${STORAGE_PREFIX}.${moduleId}.${scopeKey}`;
}

function loadProgress(moduleId: string, scopeKey: string): TourProgress | null {
  try {
    const raw = window.localStorage.getItem(storageKey(moduleId, scopeKey));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TourProgress;
    if (parsed && parsed.moduleId === moduleId) return parsed;
    return null;
  } catch {
    // Private mode / blocked storage / malformed JSON — behave as if fresh.
    return null;
  }
}

function saveProgress(scopeKey: string, progress: TourProgress): void {
  try {
    window.localStorage.setItem(
      storageKey(progress.moduleId, scopeKey),
      JSON.stringify(progress),
    );
  } catch {
    // Non-fatal: a tour that can't persist simply won't resume after refresh.
  }
}

/* ─── Mode filtering (spec §2 branch-by-mode) ─── */

/**
 * Steps whose `showForModes` excludes the active mode, or whose `hideForModes`
 * includes it, are dropped. This is how the engine guarantees it never
 * spotlights nav the workspace mode hides — the module declares the branch and
 * the controller enforces it before the step ever reaches the renderer.
 *
 * When `mode` is undefined (e.g. Module 0, before the user has chosen a mode),
 * mode-gated steps are kept — nothing is hidden yet.
 */
export function filterStepsForMode(
  steps: TourStep[],
  mode: WorkspaceMode | undefined,
): TourStep[] {
  if (!mode) return steps;
  return steps.filter((s) => {
    if (s.showForModes && !s.showForModes.includes(mode)) return false;
    if (s.hideForModes && s.hideForModes.includes(mode)) return false;
    return true;
  });
}

/* ─── Context shape ─── */

export interface TourController {
  /** The active module, or null when no tour is running. */
  module: TourModule | null;
  /** Mode-filtered steps for the active module. */
  steps: TourStep[];
  /** Current step object, or null. */
  currentStep: TourStep | null;
  /** Index into `steps`. */
  stepIndex: number;
  /** True while the spotlight overlay should render. */
  isActive: boolean;
  /** ids the user has confirmed. */
  completedStepIds: string[];
  progressStatus: TourProgress["status"];

  /** Start (or resume) a module. Resumes from saved progress unless `restart`. */
  start: (module: TourModule, opts?: { restart?: boolean }) => void;
  /** Advance to the next step (checkpoint confirm). Marks current complete. */
  next: () => void;
  /** Go back one step (does not un-complete). */
  back: () => void;
  /** Jump to an arbitrary step index — soft-gating allows jump-ahead. */
  goTo: (index: number) => void;
  /** Abandon the tour (persists `skipped`). */
  skip: () => void;
  /** Close the overlay but keep progress as `in-progress` (resume later). */
  pause: () => void;

  /**
   * True when the target index is more than one step ahead of the furthest
   * completed step — used to warn on skip-ahead (soft gate; still allowed).
   */
  isJumpAhead: (index: number) => boolean;
}

const TourContext = createContext<TourController | null>(null);

/* ─── Provider ─── */

export interface TourProviderProps {
  children: React.ReactNode;
  /**
   * Stable key for persistence — workspace id or user id. Progress is stored
   * per (module, scopeKey) so different users/workspaces resume independently.
   */
  scopeKey?: string;
  /** Active workspace mode, for branch-by-mode filtering. */
  mode?: WorkspaceMode;
}

export function TourProvider({
  children,
  scopeKey = "anon",
  mode,
}: TourProviderProps) {
  const [module, setModule] = useState<TourModule | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [isActive, setIsActive] = useState(false);
  const [completedStepIds, setCompletedStepIds] = useState<string[]>([]);
  const [progressStatus, setProgressStatus] =
    useState<TourProgress["status"]>("not-started");

  const steps = useMemo(
    () => (module ? filterStepsForMode(module.steps, mode) : []),
    [module, mode],
  );

  // Keep a ref so persistence effects read the latest without re-subscribing.
  const latest = useRef({ stepIndex, completedStepIds, progressStatus, module });
  latest.current = { stepIndex, completedStepIds, progressStatus, module };

  const persist = useCallback(
    (status: TourProgress["status"], index: number, completed: string[]) => {
      const mod = latest.current.module;
      if (!mod) return;
      saveProgress(scopeKey, {
        moduleId: mod.id,
        stepIndex: index,
        completedStepIds: completed,
        status,
        updatedAt: new Date().toISOString(),
      });
    },
    [scopeKey],
  );

  const start = useCallback<TourController["start"]>(
    (mod, opts) => {
      const filtered = filterStepsForMode(mod.steps, mode);
      const saved = opts?.restart ? null : loadProgress(mod.id, scopeKey);

      setModule(mod);
      if (saved && saved.status !== "completed") {
        const idx = Math.min(Math.max(saved.stepIndex, 0), Math.max(filtered.length - 1, 0));
        setStepIndex(idx);
        setCompletedStepIds(saved.completedStepIds ?? []);
        setProgressStatus("in-progress");
      } else {
        setStepIndex(0);
        setCompletedStepIds([]);
        setProgressStatus("in-progress");
        saveProgress(scopeKey, {
          moduleId: mod.id,
          stepIndex: 0,
          completedStepIds: [],
          status: "in-progress",
          updatedAt: new Date().toISOString(),
        });
      }
      setIsActive(true);
    },
    [mode, scopeKey],
  );

  const next = useCallback(() => {
    const step = steps[stepIndex];
    const completed = step && !completedStepIds.includes(step.id)
      ? [...completedStepIds, step.id]
      : completedStepIds;
    if (completed !== completedStepIds) setCompletedStepIds(completed);

    const nextIdx = stepIndex + 1;
    if (nextIdx >= steps.length) {
      setIsActive(false);
      setProgressStatus("completed");
      persist("completed", stepIndex, completed);
    } else {
      setStepIndex(nextIdx);
      persist("in-progress", nextIdx, completed);
    }
  }, [steps, stepIndex, completedStepIds, persist]);

  const back = useCallback(() => {
    setStepIndex((idx) => {
      const prev = Math.max(idx - 1, 0);
      persist("in-progress", prev, latest.current.completedStepIds);
      return prev;
    });
  }, [persist]);

  const goTo = useCallback(
    (index: number) => {
      setStepIndex(() => {
        const clamped = Math.min(Math.max(index, 0), Math.max(steps.length - 1, 0));
        persist("in-progress", clamped, latest.current.completedStepIds);
        return clamped;
      });
      setIsActive(true);
    },
    [steps.length, persist],
  );

  const skip = useCallback(() => {
    setIsActive(false);
    setProgressStatus("skipped");
    persist("skipped", latest.current.stepIndex, latest.current.completedStepIds);
  }, [persist]);

  const pause = useCallback(() => {
    setIsActive(false);
    persist("in-progress", latest.current.stepIndex, latest.current.completedStepIds);
  }, [persist]);

  const isJumpAhead = useCallback(
    (index: number) => {
      // Furthest completed position among the current filtered steps.
      let furthest = -1;
      steps.forEach((s, i) => {
        if (completedStepIds.includes(s.id)) furthest = Math.max(furthest, i);
      });
      return index > furthest + 1;
    },
    [steps, completedStepIds],
  );

  const value = useMemo<TourController>(
    () => ({
      module,
      steps,
      currentStep: steps[stepIndex] ?? null,
      stepIndex,
      isActive,
      completedStepIds,
      progressStatus,
      start,
      next,
      back,
      goTo,
      skip,
      pause,
      isJumpAhead,
    }),
    [
      module, steps, stepIndex, isActive, completedStepIds, progressStatus,
      start, next, back, goTo, skip, pause, isJumpAhead,
    ],
  );

  return <TourContext.Provider value={value}>{children}</TourContext.Provider>;
}

/* ─── Hook ─── */

export function useTour(): TourController {
  const ctx = useContext(TourContext);
  if (!ctx) {
    throw new Error("useTour must be used within a <TourProvider>.");
  }
  return ctx;
}

/**
 * Read persisted progress without mounting the tour — lets a page decide
 * whether to auto-start (e.g. "first visit → offer the tour"). Safe in SSR.
 */
export function peekTourProgress(
  moduleId: string,
  scopeKey: string,
): TourProgress | null {
  if (typeof window === "undefined") return null;
  return loadProgress(moduleId, scopeKey);
}
