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

interface PopoverPos {
  top: number;
  left: number;
  placement: TourPlacement;
}

/** Choose a popover position given the target rect and viewport. */
function computePopoverPos(
  rect: AnchorRect | null,
  preferred: TourPlacement,
  vw: number,
  vh: number,
  popoverH: number,
): PopoverPos {
  // No target → center it.
  if (!rect) {
    return {
      top: Math.max(GAP, vh / 2 - popoverH / 2),
      left: Math.max(GAP, vw / 2 - POPOVER_W / 2),
      placement: "auto",
    };
  }

  const spaceBelow = vh - (rect.top + rect.height);
  const spaceAbove = rect.top;
  const spaceRight = vw - (rect.left + rect.width);
  const spaceLeft = rect.left;

  let placement = preferred;
  if (placement === "auto") {
    const order: [TourPlacement, number][] = [
      ["bottom", spaceBelow],
      ["top", spaceAbove],
      ["right", spaceRight],
      ["left", spaceLeft],
    ];
    order.sort((a, b) => b[1] - a[1]);
    placement = order[0][0];
  }

  let top = 0;
  let left = 0;
  switch (placement) {
    case "top":
      top = rect.top - popoverH - GAP;
      left = rect.left + rect.width / 2 - POPOVER_W / 2;
      break;
    case "bottom":
      top = rect.top + rect.height + GAP;
      left = rect.left + rect.width / 2 - POPOVER_W / 2;
      break;
    case "left":
      top = rect.top + rect.height / 2 - popoverH / 2;
      left = rect.left - POPOVER_W - GAP;
      break;
    case "right":
    default:
      top = rect.top + rect.height / 2 - popoverH / 2;
      left = rect.left + rect.width + GAP;
      break;
  }

  // Clamp into viewport with an 8px margin.
  const M = 8;
  left = Math.min(Math.max(left, M), vw - POPOVER_W - M);
  top = Math.min(Math.max(top, M), vh - popoverH - M);
  return { top, left, placement };
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
  } = tour;

  const [mounted, setMounted] = useState(false);
  const [vw, setVw] = useState(0);
  const [vh, setVh] = useState(0);
  const [popoverH, setPopoverH] = useState(320);
  const [verifyState, setVerifyState] = useState<VerifyState>("idle");
  const [showNudge, setShowNudge] = useState<string | null>(null);
  const [prereqFailed, setPrereqFailed] = useState(false);

  const cardRef = useRef<HTMLDivElement>(null);
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

  // Measure the card so top/bottom placement accounts for real height.
  useEffect(() => {
    if (cardRef.current) setPopoverH(cardRef.current.offsetHeight);
  }, [currentStep, showNudge, prereqFailed]);

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
    () => computePopoverPos(rect, anchor?.placement ?? "auto", vw, vh, popoverH),
    [rect, anchor, vw, vh, popoverH],
  );

  if (!mounted || !isActive || !currentStep) return null;

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
            style={{ backgroundColor: "rgba(9,9,11,0.72)" }}
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
          className="absolute rounded-2xl border border-zinc-700/80 bg-zinc-900 shadow-2xl shadow-black/60 focus:outline-none pointer-events-auto"
          style={{ top: popoverPos.top, left: popoverPos.left, width: POPOVER_W, maxWidth: "calc(100vw - 16px)" }}
        >
          <div className="p-5">
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

            {/* Slot 6 — checkpoint controls */}
            <div className="flex items-center gap-2 mt-1">
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
