"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { createBrowserClient } from "@/lib/supabase";

export type JobState = "idle" | "pending" | "started" | "success" | "failure";

interface JobStatus {
  job_id: string;
  state: string;
  result?: Record<string, unknown> | null;
  error?: string | null;
}

interface UseJobPollerResult {
  state: JobState;
  result: Record<string, unknown> | null;
  error: string | null;
  start: (jobId: string) => void;
  reset: () => void;
}

const FASTAPI = process.env.NEXT_PUBLIC_FASTAPI_URL ?? "http://localhost:8000";
const POLL_MS = 2000;

export function useJobPoller(): UseJobPollerResult {
  const [state, setState] = useState<JobState>("idle");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobIdRef = useRef<string | null>(null);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const poll = useCallback(async (jobId: string) => {
    try {
      const supabase = createBrowserClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token ?? "";

      const res = await fetch(`${FASTAPI}/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;

      const status: JobStatus = await res.json();
      const s = status.state.toLowerCase();

      if (s === "success") {
        setState("success");
        setResult(status.result ?? null);
        stop();
      } else if (s === "failure") {
        setState("failure");
        setError(status.error ?? "Job failed");
        stop();
      } else if (s === "started") {
        setState("started");
      }
    } catch {
      // transient network error — keep polling
    }
  }, [stop]);

  const start = useCallback((jobId: string) => {
    stop();
    jobIdRef.current = jobId;
    setState("pending");
    setResult(null);
    setError(null);
    intervalRef.current = setInterval(() => poll(jobId), POLL_MS);
  }, [poll, stop]);

  const reset = useCallback(() => {
    stop();
    setState("idle");
    setResult(null);
    setError(null);
    jobIdRef.current = null;
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  return { state, result, error, start, reset };
}
