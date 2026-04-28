"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import { AlertTriangle, X } from "lucide-react";
import Button from "@/components/ui/Button";

interface ConfirmDialogProps {
  title?: string;
  description?: string;
  /** If provided, user must type this exact string to enable the action button */
  confirmText?: string;
  actionLabel?: string;
  onConfirm: () => void;
  onClose: () => void;
  variant?: "danger" | "warning";
}

export default function ConfirmDialog({
  title = "Final confirmation",
  description,
  confirmText,
  actionLabel = "Delete",
  onConfirm,
  onClose,
  variant = "danger",
}: ConfirmDialogProps) {
  const [input, setInput] = useState("");
  const canConfirm = confirmText ? input === confirmText : true;

  const iconRing =
    variant === "danger"
      ? "bg-rose-500/10 border-rose-500/20"
      : "bg-amber-500/10 border-amber-500/20";
  const iconColor = variant === "danger" ? "text-rose-400" : "text-amber-400";

  const handleConfirm = () => {
    if (!canConfirm) return;
    onConfirm();
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-sm rounded-2xl border border-zinc-800 bg-zinc-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close */}
        <div className="flex justify-end p-3 pb-0">
          <button
            onClick={onClose}
            className="p-1 rounded-md text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="px-6 pb-6 flex flex-col items-center gap-4 text-center">
          {/* Icon */}
          <div className={cn("flex h-12 w-12 items-center justify-center rounded-full border", iconRing)}>
            <AlertTriangle className={cn("h-5 w-5", iconColor)} />
          </div>

          {/* Copy */}
          <div>
            <h3 className="text-sm font-semibold text-zinc-100 mb-1">{title}</h3>
            {description && (
              <p className="text-xs text-zinc-500 leading-relaxed">{description}</p>
            )}
          </div>

          {/* Type-to-confirm input */}
          {confirmText && (
            <div className="w-full text-left space-y-1.5">
              <p className="text-xs text-zinc-500">
                Type{" "}
                <span className="font-mono text-zinc-300">"{confirmText}"</span>
                {" "}to confirm
              </p>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleConfirm()}
                placeholder={confirmText}
                autoFocus
                className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 outline-none focus:border-zinc-600 transition-colors"
              />
            </div>
          )}

          {/* Actions */}
          <div className="flex gap-2 w-full">
            <Button variant="secondary" className="flex-1 justify-center" onClick={onClose}>
              Cancel
            </Button>
            <button
              onClick={handleConfirm}
              disabled={!canConfirm}
              className={cn(
                "flex-1 rounded-xl px-4 py-2 text-sm font-semibold transition-all",
                variant === "danger"
                  ? "bg-rose-600 hover:bg-rose-500 text-white disabled:opacity-40 disabled:cursor-not-allowed"
                  : "bg-amber-500 hover:bg-amber-400 text-zinc-950 disabled:opacity-40 disabled:cursor-not-allowed"
              )}
            >
              {actionLabel}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
