"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Compass } from "lucide-react";
import { createBrowserClient } from "@/lib/supabase";
import type { WorkspaceMode } from "@/lib/types";
import { TourProvider, useTour, peekTourProgress } from "@/lib/onboarding/TourProvider";
import { appShellModules } from "@/lib/onboarding/modules";
import TourSpotlight from "./TourSpotlight";

/**
 * Shell-level tour host. Mounted once inside the authenticated (app) shell so
 * every post-login module (Module 1 "Your home base", and later shell modules)
 * runs with the workspace `mode` wired in for branch-by-mode filtering.
 *
 * Module 1 is auto-offered once, on the user's first visit to the dashboard,
 * and is otherwise reachable from the launcher — resuming from saved progress.
 * The engine, provider, and spotlight are unchanged; this is pure wiring.
 */

const HOME_BASE = appShellModules[0]; // Module 1 for now

/** Floating launcher + first-visit auto-offer. Must be a child of TourProvider. */
function AppTourLauncher({ scopeKey }: { scopeKey: string }) {
  const { start, isActive } = useTour();
  const pathname = usePathname();

  // Auto-offer the home-base tour once, and only on the dashboard.
  useEffect(() => {
    if (pathname !== "/dashboard") return;
    const seen = peekTourProgress(HOME_BASE.id, scopeKey);
    if (!seen) {
      const t = window.setTimeout(() => start(HOME_BASE), 800);
      return () => window.clearTimeout(t);
    }
  }, [pathname, scopeKey, start]);

  if (isActive) return null;

  return (
    <button
      type="button"
      onClick={() => start(HOME_BASE)}
      data-tour-launcher="app"
      className="fixed bottom-5 right-5 z-[60] flex items-center gap-2 rounded-full border border-indigo-500/40 bg-indigo-600/90 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-indigo-900/30 backdrop-blur hover:bg-indigo-500 transition-colors cursor-pointer"
    >
      <Compass className="h-4 w-4" />
      Product tour
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
      <AppTourLauncher scopeKey={scopeKey} />
      <TourSpotlight />
    </TourProvider>
  );
}
