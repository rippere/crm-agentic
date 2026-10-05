"use client";

import { useEffect } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import Button from "@/components/ui/Button";

// Route-level error boundary for the authenticated app. Without it, a render
// error on any (app) page (e.g. a string method on a null API field) blanks
// the whole screen with no way back except a full reload.
export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[app] render error:", error);
  }, [error]);

  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <div
        role="alert"
        className="max-w-md w-full rounded-2xl border border-zinc-800 bg-zinc-900 p-6 text-center space-y-4"
      >
        <AlertTriangle className="h-8 w-8 text-amber-400 mx-auto" aria-hidden="true" />
        <div className="space-y-1">
          <h2 className="text-base font-semibold text-zinc-100">Something went wrong</h2>
          <p className="text-sm text-zinc-400">
            This page hit an unexpected error. Your data is safe. Try again, or reload the page if it keeps happening.
          </p>
          {error.digest && (
            <p className="text-xs text-zinc-600 font-mono">Ref: {error.digest}</p>
          )}
        </div>
        <Button variant="secondary" size="sm" onClick={() => reset()}>
          <RefreshCw className="h-3.5 w-3.5 mr-1.5 inline" aria-hidden="true" />
          Try again
        </Button>
      </div>
    </div>
  );
}
