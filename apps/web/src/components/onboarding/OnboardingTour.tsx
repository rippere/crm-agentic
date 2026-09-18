"use client";

import { useEffect, useState } from "react";
import { Compass } from "lucide-react";
import { createBrowserClient } from "@/lib/supabase";
import { TourProvider, useTour, peekTourProgress } from "@/lib/onboarding/TourProvider";
import { module0Setup } from "@/lib/onboarding/modules";
import TourSpotlight from "./TourSpotlight";

/**
 * Drop-in mount for Module 0 on the onboarding page. Wires the reusable engine
 * (TourProvider + TourSpotlight) to the "Get set up" content and exposes a
 * launcher. On a user's first visit it auto-offers the tour once; after that it
 * stays a button, resuming from saved progress.
 *
 * Module 0 is intentionally mode-agnostic (the user picks their mode mid-tour),
 * so no `mode` is passed — the branch-by-mode machinery is exercised by later
 * modules that run inside the app shell.
 */

/** Floating launcher + auto-offer. Must be a child of TourProvider. */
function TourLauncher({ scopeKey }: { scopeKey: string }) {
  const tour = useTour();
  const { start, isActive } = tour;

  // Auto-offer once on first visit (no saved progress for this scope).
  useEffect(() => {
    const seen = peekTourProgress(module0Setup.id, scopeKey);
    if (!seen) {
      const t = window.setTimeout(() => start(module0Setup), 600);
      return () => window.clearTimeout(t);
    }
  }, [scopeKey, start]);

  if (isActive) return null;

  return (
    <button
      type="button"
      onClick={() => start(module0Setup)}
      data-tour-launcher
      className="fixed bottom-5 right-5 z-[60] flex items-center gap-2 rounded-full border border-indigo-500/40 bg-indigo-600/90 px-4 py-2.5 text-sm font-medium text-white shadow-lg shadow-indigo-900/30 backdrop-blur hover:bg-indigo-500 transition-colors cursor-pointer"
    >
      <Compass className="h-4 w-4" />
      Guided setup
    </button>
  );
}

export default function OnboardingTour() {
  const [scopeKey, setScopeKey] = useState("anon");

  // Best-effort per-user scope so progress resumes for the right person.
  // Wrapped defensively: createBrowserClient() throws synchronously when
  // Supabase env is absent, and the tour must never take the onboarding page
  // down over a missing scope key — it just falls back to "anon".
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
    <TourProvider scopeKey={scopeKey}>
      <TourLauncher scopeKey={scopeKey} />
      <TourSpotlight />
    </TourProvider>
  );
}
