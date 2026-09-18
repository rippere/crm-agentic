"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { Compass } from "lucide-react";
import { createBrowserClient } from "@/lib/supabase";
import type { WorkspaceMode } from "@/lib/types";
import { TourProvider, useTour, peekTourProgress, filterStepsForMode } from "@/lib/onboarding/TourProvider";
import { activationModules, level2Modules, capstoneModules, moduleHomeRoutes } from "@/lib/onboarding/modules";
import type { TourModule } from "@/lib/onboarding/types";
import TourSpotlight from "./TourSpotlight";

/**
 * Shell-level tour host. Mounted once inside the authenticated (app) shell so
 * every post-login shell module (Module 1 "Your home base", Module 2 "Contacts",
 * Module 3 "Inbox & Calls", the Sales/PM tracks) runs with the workspace `mode`
 * wired in for branch-by-mode filtering.
 *
 * First-run modules are auto-offered once, on first visit to their home route,
 * and reachable from the launcher, which resumes the first not-yet-completed
 * one. The Level-2 capstone (C1-C3) is NOT auto-offered and has no home route —
 * it's "unlocked later": the launcher only offers it once every applicable
 * first-run module is complete. The engine/provider/spotlight are unchanged.
 */

/** Does this module have any steps for the current workspace mode? */
function appliesToMode(module: TourModule, mode: WorkspaceMode): boolean {
  return filterStepsForMode(module.steps, mode).length > 0;
}

function isCompleted(scopeKey: string, m: TourModule): boolean {
  return peekTourProgress(m.id, scopeKey)?.status === "completed";
}

/** Activation-core modules that apply to this mode (the only ones auto-offered). */
function activationForMode(mode: WorkspaceMode): TourModule[] {
  return activationModules.filter((m) => appliesToMode(m, mode));
}

/** The full first-run curriculum (activation core → level-2) for this mode. */
function firstRunForMode(mode: WorkspaceMode): TourModule[] {
  return [...activationModules, ...level2Modules].filter((m) => appliesToMode(m, mode));
}

/**
 * What the launcher starts: walk the first-run curriculum in order (activation
 * core first, then level-2) and return the first module the user hasn't
 * completed. ONLY once every first-run module is complete does it unlock the
 * capstone (first uncompleted capstone module). Level-2 and the capstone are
 * never auto-offered — this launcher is the sole path past the activation core.
 */
function launcherTarget(scopeKey: string, mode: WorkspaceMode): TourModule {
  const firstRun = firstRunForMode(mode);
  const unfinished = firstRun.find((m) => !isCompleted(scopeKey, m));
  if (unfinished) return unfinished;
  const unfinishedCapstone = capstoneModules.find((m) => !isCompleted(scopeKey, m));
  return unfinishedCapstone ?? capstoneModules[capstoneModules.length - 1] ?? firstRun[firstRun.length - 1];
}

/** True once every activation-core module for the mode is complete. */
function activationComplete(scopeKey: string, mode: WorkspaceMode): boolean {
  return activationForMode(mode).every((m) => isCompleted(scopeKey, m));
}

/** True once every first-run module (core + level-2) is complete (capstone unlocked). */
function firstRunComplete(scopeKey: string, mode: WorkspaceMode): boolean {
  return firstRunForMode(mode).every((m) => isCompleted(scopeKey, m));
}

/**
 * Milestone headlines keyed by the module whose completion earns them: finishing
 * the activation core, and finishing the whole first-run curriculum. TourProvider
 * looks these up when a module completes and shows a louder celebration card.
 */
function milestonesForMode(mode: WorkspaceMode): Record<string, string> {
  const core = activationForMode(mode);
  const firstRun = firstRunForMode(mode);
  const out: Record<string, string> = {};
  const lastCore = core[core.length - 1];
  const lastFirstRun = firstRun[firstRun.length - 1];
  if (lastCore) out[lastCore.id] = "🎉 Your CRM is set up";
  if (lastFirstRun) out[lastFirstRun.id] = "🎉 You've got the essentials down";
  return out;
}

/** Floating launcher + first-visit-per-route auto-offer. Child of TourProvider. */
function AppTourLauncher({ scopeKey, mode }: { scopeKey: string; mode: WorkspaceMode }) {
  const { start, isActive } = useTour();
  const pathname = usePathname();
  const router = useRouter();

  // Auto-offer ONLY the activation-core module whose home route matches this page
  // (and applies to the mode, and is unseen). Level-2 and the capstone are never
  // auto-offered — they are reached from the launcher once the core is complete,
  // so first-run never dumps 30 steps on a brand-new user.
  useEffect(() => {
    const module = activationModules.find((m) => moduleHomeRoutes[m.id] === pathname);
    if (!module || !appliesToMode(module, mode)) return;
    const seen = peekTourProgress(module.id, scopeKey);
    if (!seen) {
      const t = window.setTimeout(() => start(module), 800);
      return () => window.clearTimeout(t);
    }
  }, [pathname, scopeKey, mode, start]);

  if (isActive) return null;

  const coreDone = activationComplete(scopeKey, mode);
  const allDone = firstRunComplete(scopeKey, mode);
  // Three states: fresh user → "Product tour"; core done, more first-run left →
  // "Continue tour"; everything but the capstone done → "Advanced tour".
  const label = !coreDone ? "Product tour" : !allDone ? "Continue tour" : "Advanced tour";

  const launch = () => {
    const target = launcherTarget(scopeKey, mode);
    // Land on the module's home page first so its steps anchor to real elements
    // instead of centering until the user happens to navigate there.
    const home = moduleHomeRoutes[target.id];
    if (home && pathname !== home) router.push(home);
    start(target);
  };

  return (
    <button
      type="button"
      onClick={launch}
      data-tour-launcher="app"
      data-capstone-unlocked={allDone ? "true" : "false"}
      className="fixed bottom-5 right-5 z-[60] flex items-center gap-2 rounded-full border border-indigo-500/40 bg-indigo-600/90 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-indigo-900/30 backdrop-blur hover:bg-indigo-500 transition-colors cursor-pointer"
    >
      <Compass className="h-4 w-4" />
      {label}
    </button>
  );
}

export default function AppTour({ mode }: { mode: WorkspaceMode }) {
  const [scopeKey, setScopeKey] = useState("anon");

  // Best-effort per-user scope, matching OnboardingTour so Module 0 and the
  // shell modules resume under the same key. Guarded: createBrowserClient()
  // throws synchronously without Supabase env, and the tour must never take the
  // app shell down over a missing scope key.
  useEffect(() => {
    let cancelled = false;
    try {
      createBrowserClient()
        .auth.getUser()
        .then(({ data }) => {
          if (!cancelled && data.user?.id) setScopeKey(data.user.id);
        })
        .catch(() => { /* fall back to "anon" */ });
    } catch {
      /* no client available — keep "anon" scope */
    }
    return () => { cancelled = true; };
  }, []);

  return (
    <TourProvider
      scopeKey={scopeKey}
      mode={mode}
      curriculumOrder={firstRunForMode(mode)}
      milestones={milestonesForMode(mode)}
    >
      <AppTourLauncher scopeKey={scopeKey} mode={mode} />
      <TourSpotlight />
    </TourProvider>
  );
}
