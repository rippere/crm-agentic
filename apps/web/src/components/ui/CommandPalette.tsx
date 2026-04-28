"use client";

import { useEffect, useRef, useCallback, useState } from "react";
import { cn } from "@/lib/utils";
import {
  ArrowUp, Paperclip, X, Brain, Mail, Users,
  ClipboardList, Plus, Sparkles, Loader2,
} from "lucide-react";

function useAutoResizeTextarea({ minHeight, maxHeight }: { minHeight: number; maxHeight?: number }) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const adjust = useCallback(
    (reset?: boolean) => {
      const el = ref.current;
      if (!el) return;
      el.style.height = `${minHeight}px`;
      if (!reset) {
        const h = Math.max(minHeight, Math.min(el.scrollHeight, maxHeight ?? Infinity));
        el.style.height = `${h}px`;
      }
    },
    [minHeight, maxHeight]
  );
  useEffect(() => {
    if (ref.current) ref.current.style.height = `${minHeight}px`;
  }, [minHeight]);
  return { ref, adjust };
}

const CRM_CHIPS = [
  { icon: <Brain className="h-3.5 w-3.5" />, label: "Summarize Deal" },
  { icon: <Mail className="h-3.5 w-3.5" />, label: "Draft Follow-up" },
  { icon: <Users className="h-3.5 w-3.5" />, label: "Find Contact" },
  { icon: <ClipboardList className="h-3.5 w-3.5" />, label: "Log Activity" },
  { icon: <Plus className="h-3.5 w-3.5" />, label: "New Deal" },
  { icon: <Sparkles className="h-3.5 w-3.5" />, label: "AI Enrichment" },
];

interface CommandPaletteProps {
  onClose: () => void;
  onSubmit?: (value: string) => void;
}

export default function CommandPalette({ onClose, onSubmit }: CommandPaletteProps) {
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);
  const { ref, adjust } = useAutoResizeTextarea({ minHeight: 60, maxHeight: 200 });

  useEffect(() => {
    ref.current?.focus();
  }, [ref]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [onClose]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!value.trim() || loading) return;
    setLoading(true);
    onSubmit?.(value.trim());
    setTimeout(() => {
      setLoading(false);
      setValue("");
      adjust(true);
    }, 2000);
  };

  const handleChip = (label: string) => {
    setValue(label + ": ");
    ref.current?.focus();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-2xl font-bold text-white tracking-tight">
            What can I help you{" "}
            <span className="text-indigo-400">close?</span>
          </h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Input box */}
        <div className="relative rounded-2xl border border-zinc-700/80 bg-zinc-900 shadow-[0_0_40px_rgba(99,102,241,0.12)]">
          <div className="overflow-y-auto">
            <textarea
              ref={ref}
              value={value}
              onChange={(e) => { setValue(e.target.value); adjust(); }}
              onKeyDown={handleKeyDown}
              placeholder="Ask anything about your deals, contacts, or pipeline…"
              className={cn(
                "w-full px-5 py-4 resize-none bg-transparent border-none outline-none",
                "text-zinc-100 text-sm leading-relaxed",
                "placeholder:text-zinc-600 min-h-[60px]"
              )}
              style={{ overflow: "hidden" }}
            />
          </div>

          <div className="flex items-center justify-between px-4 pb-4 pt-1">
            <button
              type="button"
              title="Attach file"
              className="p-2 rounded-lg text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800 transition-colors"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!value.trim() || loading}
              className={cn(
                "flex items-center justify-center h-8 w-8 rounded-lg transition-all",
                value.trim() && !loading
                  ? "bg-indigo-600 hover:bg-indigo-500 text-white shadow-[0_0_12px_rgba(99,102,241,0.4)]"
                  : "bg-zinc-800 text-zinc-600 cursor-not-allowed"
              )}
              aria-label="Send"
            >
              {loading
                ? <Loader2 className="h-4 w-4 animate-spin" />
                : <ArrowUp className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {/* CRM Action chips */}
        <div className="flex flex-wrap items-center justify-center gap-2 mt-4">
          {CRM_CHIPS.map(({ icon, label }) => (
            <button
              key={label}
              type="button"
              onClick={() => handleChip(label)}
              className="flex items-center gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 rounded-full border border-zinc-800 hover:border-zinc-700 text-zinc-400 hover:text-zinc-200 transition-all text-xs font-medium"
            >
              <span className="text-indigo-400">{icon}</span>
              {label}
            </button>
          ))}
        </div>

        <p className="text-center text-[11px] text-zinc-700 mt-3 font-mono">
          <kbd className="px-1.5 py-0.5 rounded border border-zinc-800 bg-zinc-900 text-zinc-600">⌘K</kbd>
          {" "}to toggle · {" "}
          <kbd className="px-1.5 py-0.5 rounded border border-zinc-800 bg-zinc-900 text-zinc-600">ESC</kbd>
          {" "}to close
        </p>
      </div>
    </div>
  );
}
