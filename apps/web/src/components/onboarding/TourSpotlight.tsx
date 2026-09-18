"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ArrowLeft, ArrowRight, Check, HelpCircle, Sparkles, X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useTour } from "@/lib/onboarding/TourProvider";
import type { TourPlacement, VerifyState } from "@/lib/onboarding/types";
import { useAnchorRect, type AnchorRect } from "./useAnchorRect";

/* ─── Popover geometry ─── */

const POPOVER_W = 360;
const GAP = 16; // px between spotlight and popover
const MIN_SIDE = 140; // smallest height we'll squeeze the card into a tight gap

interface PopoverPos {
  /** Exactly one of top/bottom is set — CSS anchoring for the absolute card. */
  top?: number;
  bottom?: number;
  left: number;
  placement: TourPlacement;
  /** Cap the card height so it fits its side without covering the anchor. */
  maxHeight: number;
}

/**
 * Choose a popover position that never covers the highlighted control.
 *
 * The card can be tall (six slots). On a small viewport it won't fit whole above
 * or below the anchor, so instead of letting it blanket the form we cap its
 * HEIGHT to the room on its chosen side and let it scroll internally — the anchor
 * always stays visible. A horizontal side (beside the anchor) is preferred when
 * the card's full width fits there, since that keeps near-full height.
 */
function computePopoverPos(
  rect: AnchorRect | null,
  vw: number,
  vh: number,
): PopoverPos {
  const M = 8;
  const fullH = vh - 2 * M;
  const clampX = (x: number) => Math.min(Math.max(x, M), vw - POPOVER_W - M);

  // No target on screen (control not mounted, or the wizard advanced past this
  // step) → dock to the BOTTOM so a centered form behind the coach-mark stays
  // visible instead of being buried under the card.
  if (!rect) {
    return { bottom: GAP, left: clampX(vw / 2 - POPOVER_W / 2), placement: "auto", maxHeight: fullH };
  }

  const aTop = rect.top;
  const aBottom = rect.top + rect.height;
  const aLeft = rect.left;
  const aRight = rect.left + rect.width;
  const roomBelow = vh - aBottom - GAP - M;
  const roomAbove = aTop - GAP - M;
  const roomRight = vw - aRight - GAP - M;
  const roomLeft = aLeft - GAP - M;
  const cx = clampX(aLeft + rect.width / 2 - POPOVER_W / 2);

  // 1) Beside the anchor when the card's full WIDTH fits → near-full height,
  //    starting around the anchor's top and scrolling if long.
  if (roomRight >= POPOVER_W || roomLeft >= POPOVER_W) {
    const right = roomRight >= roomLeft;
    const top = Math.min(Math.max(aTop, M), vh - MIN_SIDE - M);
    return {
      top,
      left: right ? aRight + GAP : aLeft - POPOVER_W - GAP,
      placement: right ? "right" : "left",
      maxHeight: vh - top - M,
    };
  }

  // 2) Otherwise the vertical side with more room, anchored by the edge FACING
  //    the anchor (top → pin the card's bottom; bottom → pin its top) so the
  //    card grows AWAY from the anchor and its height is irrelevant to overlap.
  //    Height is capped to the room, so it scrolls internally instead of
  //    spilling over the control.
  if (roomBelow >= roomAbove) {
    return { top: aBottom + GAP, left: cx, placement: "bottom", maxHeight: Math.max(MIN_SIDE, roomBelow) };
  }
  return { bottom: vh - aTop + GAP, left: cx, placement: "top", maxHeight: Math.max(MIN_SIDE, roomAbove) };
}

/* ─── Overlay ─── */

/**
 * The reusable spotlight layer. Renders through a portal:
 *   - a full-screen backdrop with a cut-out highlight around the target
 *     (box-shadow "hole" technique — animates cleanly, no SVG mask needed);
 *   - an anchored popover card built from the current step's six slots.
 *
 * Accessibility: the popover is a focus-trapped dialog; Esc pauses the tour,
 * the close button skips it, and focus moves to the card on each step.
 *
 * Renders nothing unless a tour is active. Mount it once, inside a TourProvider.
 */
export default function TourSpotlight() {
  const tour = useTour();
  const {
    currentStep, stepIndex, steps, isActive, completedStepIds,
    next, back, skip, pause, isJumpAhead, goTo,
    curriculum, completion, dismissCompletion,
  } = tour;

  const [mounted, setMounted] = useState(false);
  const [vw, setVw] = useState(0);
  const [vh, setVh] = useState(0);
  const [verifyState, setVerifyState] = useState<VerifyState>("idle");
  const [showNudge, setShowNudge] = useState<string | null>(null);
  const [prereqFailed, setPrereqFailed] = useState(false);

  const cardRef = useRef<HTMLDivElement>(null);
  const completionCardRef = useRef<HTMLDivElement>(null);
  const confirmAttempted = useRef(false);

  useEffect(() => setMounted(true), []);

  // Track viewport size.
  useEffect(() => {
    if (!isActive) return;
    const update = () => {
      setVw(window.innerWidth);
      setVh(window.innerHeight);
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [isActive]);

  const anchor = currentStep?.anchor ?? null;
  const rect = useAnchorRect(
    isActive && anchor ? anchor.selector : null,
    isActive,
    anchor?.padding ?? 8,
  );

  // Reset per-step transient UI + run the soft prerequisite check.
  useEffect(() => {
    confirmAttempted.current = false;
    setShowNudge(null);
    setVerifyState("idle");
    setPrereqFailed(false);

    const pre = currentStep?.prerequisiteCheck;
    if (!pre?.verify) return;
    let cancelled = false;
    // Re-check on a short poll: prerequisite targets (like anchors) can mount
    // AFTER the step is entered as the underlying wizard advances, so a one-shot
    // check would leave a stale nudge. Stops polling once satisfied.
    const run = () => {
      Promise.resolve(pre.verify!())
        .then((ok) => {
          if (cancelled) return;
          setPrereqFailed(!ok);
          if (ok) window.clearInterval(timer);
        })
        .catch(() => { /* soft: ignore check errors */ });
    };
    run();
    const timer = window.setInterval(run, 400);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [currentStep]);

  // Keyboard: Esc pauses; focus trap keeps Tab inside the card.
  useEffect(() => {
    if (!isActive) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        pause();
        return;
      }
      if (e.key === "Tab" && cardRef.current) {
        const focusable = cardRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isActive, pause]);

  // Move focus to the card when the step changes.
  useEffect(() => {
    if (isActive && cardRef.current) {
      const t = window.setTimeout(() => cardRef.current?.focus(), 50);
      return () => window.clearTimeout(t);
    }
  }, [isActive, stepIndex]);

  // The completion celebration is a real modal (aria-modal), but `isActive` is
  // already false by the time it shows, so the step popover's keydown trap above
  // doesn't cover it. Give it its own Esc-to-dismiss + Tab focus-trap so keyboard
  // and AT users can't tab out into the (only visually covered) page behind it.
  useEffect(() => {
    if (!completion) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        dismissCompletion();
        return;
      }
      if (e.key === "Tab") {
        const focusable = completionCardRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, [tabindex]:not([tabindex="-1"])',
        );
        if (!focusable || focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [completion, dismissCompletion]);

  const handleConfirm = useCallback(async () => {
    const cp = currentStep?.checkpoint;
    // Soft-verify: on the FIRST confirm, if the check fails, nudge but don't block.
    if (cp?.verify && !confirmAttempted.current) {
      confirmAttempted.current = true;
      setVerifyState("checking");
      try {
        const ok = await Promise.resolve(cp.verify());
        if (!ok) {
          setVerifyState("failed");
          setShowNudge(cp.nudge ?? "We couldn't confirm that yet — you can continue anyway.");
          return; // second click will advance
        }
        setVerifyState("ok");
      } catch {
        setVerifyState("idle"); // soft: never block on a thrown check
      }
    }
    next();
  }, [currentStep, next]);

  const popoverPos = useMemo(
    () => computePopoverPos(rect, vw, vh),
    [rect, vw, vh],
  );

  if (!mounted) return null;

  // Celebration card — shown once a module completes (isActive is already false).
  // A brief, explicit reward that the plain "overlay unmounts" flow never gave.
  if (completion) {
    return createPortal(
      <div
        className="fixed inset-0 z-[100] flex items-center justify-center p-4"
        style={{ backgroundColor: "rgba(9,9,11,0.72)" }}
      >
        <motion.div
          ref={completionCardRef}
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.22, ease: "easeOut" }}
          role="dialog"
          aria-modal="true"
          aria-label="Module complete"
          className="w-[360px] max-w-[calc(100vw-16px)] rounded-2xl border border-indigo-500/40 bg-zinc-900 p-6 text-center shadow-2xl shadow-black/60"
        >
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-indigo-500/40 bg-indigo-500/15">
            <Check className="h-7 w-7 text-indigo-400" />
          </div>
          <h2 className="mb-1 text-lg font-semibold text-zinc-100">{completion.headline}</h2>
          <p className="mb-4 text-sm leading-relaxed text-zinc-400">
            {completion.isFinale
              ? "You've finished the essentials — your workspace is set up and running on real data. Explore anytime; the launcher can replay any part."
              : `Nice work — ${completion.moduleTitle} done.`}
          </p>
          <div className="mb-1 h-1.5 w-full overflow-hidden rounded-full bg-zinc-800">
            <div
              className="h-full rounded-full bg-indigo-500 transition-all"
              style={{ width: `${completion.percent}%` }}
            />
          </div>
          <p className="mb-5 text-xs text-zinc-500">{completion.percent}% of setup complete</p>
          <button
            type="button"
            onClick={dismissCompletion}
            autoFocus
            className="flex w-full items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-indigo-500 cursor-pointer"
          >
            {completion.isFinale
              ? <>Done <Check className="h-4 w-4" /></>
              : <>Keep going <ArrowRight className="h-4 w-4" /></>}
          </button>
        </motion.div>
      </div>,
      document.body,
    );
  }

  if (!isActive || !currentStep) return null;

  const jumpAhead = isJumpAhead(stepIndex);
  const isLast = stepIndex === steps.length - 1;
  const step = currentStep;

  const overlay = (
    // pointer-events-none so the REAL wizard controls under the dim stay fully
    // interactive (the tour is a non-blocking coach-mark, not a modal). Only the
    // popover card below re-enables pointer events.
    <div
      className="fixed inset-0 z-[100] pointer-events-none"
      role="presentation"
    >
      {/* Backdrop + cut-out. A single motion.div sized to the target casts a
          huge box-shadow, darkening everything except the highlighted element. */}
      <AnimatePresence>
        {rect ? (
          <motion.div
            key="spotlight"
            className="absolute rounded-xl pointer-events-none"
            initial={false}
            animate={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }}
            transition={{ type: "spring", stiffness: 320, damping: 34 }}
            style={{
              boxShadow: "0 0 0 9999px rgba(9,9,11,0.72), 0 0 0 1px rgba(129,140,248,0.5)",
            }}
          />
        ) : (
          <motion.div
            key="dim"
            className="absolute inset-0 pointer-events-none"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            // Lighter than the spotlight dim: with no cut-out the whole screen is
            // dimmed, so keep the form behind the coach-mark clearly readable.
            style={{ backgroundColor: "rgba(9,9,11,0.55)" }}
          />
        )}
      </AnimatePresence>

      {/* Popover card — the only pointer-interactive part of the overlay. */}
      <AnimatePresence mode="wait">
        <motion.div
          key={step.id}
          ref={cardRef}
          role="dialog"
          aria-modal="false"
          aria-labelledby="tour-title"
          aria-describedby="tour-why"
          tabIndex={-1}
          initial={{ opacity: 0, scale: 0.96, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -8 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="absolute rounded-2xl border border-zinc-700/80 bg-zinc-900 shadow-2xl shadow-black/60 focus:outline-none pointer-events-auto overflow-y-auto overscroll-contain"
          // Cap to the viewport and scroll internally so a content-heavy step
          // (six slots + AI tip) never pushes its checkpoint buttons off-screen
          // on a short viewport. popoverH is measured from this capped height,
          // so placement uses the real on-screen size.
          style={{
            ...(popoverPos.top !== undefined ? { top: popoverPos.top } : { bottom: popoverPos.bottom }),
            left: popoverPos.left,
            width: POPOVER_W,
            maxWidth: "calc(100vw - 16px)",
            maxHeight: `${popoverPos.maxHeight}px`,
          }}
        >
          <div className="p-5">
            {/* Curriculum progress (Module N of M) — the cross-module momentum
                the per-module step dots below can't show. Absent for Module 0. */}
            {curriculum && (
              <div className="mb-3">
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-zinc-500">
                    Module {curriculum.moduleIndex + 1} of {curriculum.moduleCount}
                  </span>
                  <span className="text-[10px] font-mono font-semibold text-indigo-400">
                    {curriculum.percent}%
                  </span>
                </div>
                <div className="h-1 w-full overflow-hidden rounded-full bg-zinc-800">
                  <div
                    className="h-full rounded-full bg-indigo-500/70 transition-all"
                    style={{ width: `${curriculum.percent}%` }}
                  />
                </div>
              </div>
            )}

            {/* Header: progress + close */}
            <div className="flex items-center justify-between mb-3">
              <span className="text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-indigo-400">
                Step {stepIndex + 1} of {steps.length}
              </span>
              <button
                type="button"
                onClick={skip}
                aria-label="Skip tour"
                className="flex h-6 w-6 items-center justify-center rounded-md text-zinc-500 hover:text-zinc-200 hover:bg-zinc-800 transition-colors cursor-pointer"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Progress dots (jump-ahead allowed via click — soft gate) */}
            <div className="flex items-center gap-1.5 mb-4">
              {steps.map((s, i) => {
                const done = completedStepIds.includes(s.id);
                const isCurrent = i === stepIndex;
                return (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => goTo(i)}
                    aria-label={`Go to step ${i + 1}`}
                    className={cn(
                      "h-1.5 rounded-full transition-all cursor-pointer",
                      isCurrent ? "w-6 bg-indigo-500" : done ? "w-1.5 bg-indigo-500/60" : "w-1.5 bg-zinc-700 hover:bg-zinc-600",
                    )}
                  />
                );
              })}
            </div>

            {/* Slot 1 — why this exists */}
            <h2 id="tour-title" className="text-base font-semibold text-zinc-100 mb-1.5">
              {step.title}
            </h2>
            <p id="tour-why" className="text-sm text-zinc-400 leading-relaxed mb-3">
              {step.whyThisExists}
            </p>

            {/* Slot 2 — prerequisite check (soft) */}
            {step.prerequisiteCheck && (
              <div className={cn(
                "flex items-start gap-2 rounded-lg border px-3 py-2 mb-3 text-xs",
                prereqFailed
                  ? "border-amber-500/30 bg-amber-500/5 text-amber-300"
                  : "border-zinc-800 bg-zinc-800/40 text-zinc-400",
              )}>
                <Check className={cn("h-3.5 w-3.5 mt-0.5 shrink-0", prereqFailed ? "text-amber-400" : "text-zinc-500")} />
                <span>
                  {prereqFailed && step.prerequisiteCheck.nudge
                    ? step.prerequisiteCheck.nudge
                    : step.prerequisiteCheck.label}
                </span>
              </div>
            )}

            {/* Slot 4 — action guidance */}
            <div className="rounded-lg bg-indigo-500/5 border border-indigo-500/20 px-3 py-2.5 mb-3">
              <p className="text-[10px] font-mono font-semibold uppercase tracking-wider text-indigo-400 mb-1">Do this</p>
              <p className="text-sm text-zinc-200 leading-relaxed">{step.actionGuidance}</p>
            </div>

            {/* Slot 5 — what just happened + forward reference */}
            <p className="text-xs text-zinc-500 leading-relaxed mb-1">{step.whatJustHappened}</p>
            {step.forwardReference && (
              <p className="flex items-start gap-1.5 text-xs text-zinc-500 leading-relaxed mb-3">
                <ArrowRight className="h-3 w-3 mt-0.5 shrink-0 text-zinc-600" />
                <span>{step.forwardReference}</span>
              </p>
            )}

            {/* AI-tip slot (mechanism only; renders when a module supplies text) */}
            {step.aiTip?.text && (
              <div className="flex items-start gap-2 rounded-lg border border-indigo-500/20 bg-indigo-500/5 px-3 py-2 mb-3">
                <Sparkles className="h-3.5 w-3.5 mt-0.5 shrink-0 text-indigo-400" />
                <p className="text-xs text-indigo-200/90 leading-relaxed">{step.aiTip.text}</p>
              </div>
            )}

            {/* Soft nudge (checkpoint verify failed once) */}
            {showNudge && (
              <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 mb-3 text-xs text-amber-300">
                <HelpCircle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-amber-400" />
                <span>{showNudge}</span>
              </div>
            )}

            {/* Jump-ahead warning (soft gate) */}
            {jumpAhead && (
              <p className="text-[11px] text-amber-400/80 mb-3">
                You&apos;ve jumped ahead — earlier steps aren&apos;t marked done yet. That&apos;s fine, just so you know.
              </p>
            )}

            {/* Slot 6 — checkpoint controls. Sticky footer so the confirm/Back
                buttons stay reachable when the card's height is capped and its
                content scrolls on a small viewport. */}
            <div className="sticky bottom-0 -mx-5 -mb-5 mt-2 flex items-center gap-2 border-t border-zinc-800 bg-zinc-900 px-5 py-3">
              <button
                type="button"
                onClick={back}
                disabled={stepIndex === 0}
                className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:border-zinc-600 disabled:opacity-40 disabled:cursor-not-allowed transition cursor-pointer"
              >
                <ArrowLeft className="h-3.5 w-3.5" /> Back
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                className="flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-500 transition cursor-pointer"
              >
                {verifyState === "checking"
                  ? "Checking…"
                  : isLast
                    ? <>Finish <Check className="h-4 w-4" /></>
                    : <>{step.checkpoint.confirmLabel} <ArrowRight className="h-4 w-4" /></>}
              </button>
            </div>
          </div>
        </motion.div>
      </AnimatePresence>
    </div>
  );

  return createPortal(overlay, document.body);
}
