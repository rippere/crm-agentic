"use client";

import { useEffect, useState } from "react";

export interface AnchorRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

/**
 * Resolve a DOM element by selector and track its viewport rect, keeping it
 * fresh across scroll, resize, and layout mutations. Returns null while the
 * target is absent (e.g. it hasn't mounted yet because the user is on an
 * earlier wizard sub-step) — the overlay renders a centered popover in that case.
 *
 * The target is polled because tour anchors mount/unmount as the underlying UI
 * advances; a MutationObserver alone misses elements added before this mounts,
 * and a one-shot query misses elements added later.
 */
export function useAnchorRect(
  selector: string | null,
  active: boolean,
  scrollPadding = 12,
): AnchorRect | null {
  const [rect, setRect] = useState<AnchorRect | null>(null);

  useEffect(() => {
    if (!active || !selector || typeof document === "undefined") {
      setRect(null);
      return;
    }

    let raf = 0;
    let poll = 0;
    let scrolledInto = false;
    let lastEl: Element | null = null;

    const measure = () => {
      const el = document.querySelector(selector);
      if (!el) {
        lastEl = null;
        setRect(null);
        return;
      }
      if (el !== lastEl) {
        lastEl = el;
        scrolledInto = false;
      }
      if (!scrolledInto) {
        scrolledInto = true;
        el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      }
      const r = el.getBoundingClientRect();
      setRect({
        top: r.top - scrollPadding,
        left: r.left - scrollPadding,
        width: r.width + scrollPadding * 2,
        height: r.height + scrollPadding * 2,
      });
    };

    const schedule = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    };

    // Initial + continuous.
    schedule();
    poll = window.setInterval(schedule, 250); // catch mount/unmount + smooth-scroll settle

    window.addEventListener("resize", schedule);
    window.addEventListener("scroll", schedule, true); // capture: catch scrolls in any container

    const mo = new MutationObserver(schedule);
    mo.observe(document.body, { childList: true, subtree: true, attributes: true });

    return () => {
      cancelAnimationFrame(raf);
      window.clearInterval(poll);
      window.removeEventListener("resize", schedule);
      window.removeEventListener("scroll", schedule, true);
      mo.disconnect();
    };
  }, [selector, active, scrollPadding]);

  return rect;
}
