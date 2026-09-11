"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Compass } from "lucide-react";
import { createBrowserClient } from "@/lib/supabase";
import type { WorkspaceMode } from "@/lib/types";
import { TourProvider, useTour, peekTourProgress, filterStepsForMode } from "@/lib/onboarding/TourProvider";
import { appShellModules, capstoneModules, moduleHomeRoutes } from "@/lib/onboarding/modules";
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

/**
 * What the launcher starts: the first not-yet-completed first-run module for the
 * mode; and ONLY once every first-run module is complete does it unlock the
 * capstone (first uncompleted capstone module). This is the sole path to the
 * capstone — it is never auto-offered and never surfaces on first run.
 */
function launcherTarget(scopeKey: string, mode: WorkspaceMode): TourModule {
  const firstRun = appShellModules.filter((m) => appliesToMode(m, mode));
  const unfinishedFirstRun = firstRun.find((m) => !isCompleted(scopeKey, m));
  if (unfinishedFirstRun) return unfinishedFirstRun;
  // First-run complete → unlock capstone.
  const unfinishedCapstone = capstoneModules.find((m) => !isCompleted(scopeKey, m));
  return unfinishedCapstone ?? capstoneModules[capstoneModules.length - 1] ?? firstRun[firstRun.length - 1];
}

/** True once every applicable first-run module is complete (capstone unlocked). */
function capstoneUnlocked(scopeKey: string, mode: WorkspaceMode): boolean {
  return appShellModules.filter((m) => appliesToMode(m, mode)).every((m) => isCompleted(scopeKey, m));
}

/** Floating launcher + first-visit-per-route auto-offer. Child of TourProvider. */
function AppTourLauncher({ scopeKey, mode }: { scopeKey: string; mode: WorkspaceMode }) {
  const { start, isActive } = useTour();
  const pathname = usePathname();

  // Auto-offer the module whose home route matches this page — but only if it
  // applies to the current mode (a PM-only module is never offered in a Sales
  // workspace) and hasn't been seen yet.
  useEffect(() => {
    const module = appShellModules.find((m) => moduleHomeRoutes[m.id] === pathname);
    if (!module || !appliesToMode(module, mode)) return;
    const seen = peekTourProgress(module.id, scopeKey);
    if (!seen) {
      const t = window.setTimeout(() => start(module), 800);
      return () => window.clearTimeout(t);
    }
  }, [pathname, scopeKey, mode, start]);

  if (isActive) return null;

  // Once first-run is done, the launcher unlocks the Level-2 capstone.
  const unlocked = capstoneUnlocked(scopeKey, mode);

  return (
    <button
      type="button"
      onClick={() => start(launcherTarget(scopeKey, mode))}
      data-tour-launcher="app"
      data-capstone-unlocked={unlocked ? "true" : "false"}
      className="fixed bottom-5 right-5 z-[60] flex items-center gap-2 rounded-full border border-indigo-500/40 bg-indigo-600/90 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-indigo-900/30 backdrop-blur hover:bg-indigo-500 transition-colors cursor-pointer"
    >
      <Compass className="h-4 w-4" />
      {unlocked ? "Advanced tour" : "Product tour"}
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
    <TourProvider scopeKey={scopeKey} mode={mode}>
      <AppTourLauncher scopeKey={scopeKey} mode={mode} />
      <TourSpotlight />
    </TourProvider>
  );
}
