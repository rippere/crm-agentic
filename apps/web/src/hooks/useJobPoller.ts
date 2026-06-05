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
// Stop after this many consecutive network/HTTP errors so a dead API doesn't
// poll forever.
const MAX_CONSECUTIVE_FAILURES = 5;
// Hard ceiling on total polls (~60 × 2s = 2 min) so even a job that is wedged
// PENDING server-side eventually stops the poller instead of running for the
// life of the page.
const MAX_POLLS = 60;

export function useJobPoller(): UseJobPollerResult {
  const [state, setState] = useState<JobState>("idle");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const jobIdRef = useRef<string | null>(null);
  const failuresRef = useRef(0);
  const pollsRef = useRef(0);

  const stop = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const poll = useCallback(async (jobId: string) => {
    // Absolute cap — give up even if the server keeps saying PENDING.
    pollsRef.current += 1;
    if (pollsRef.current > MAX_POLLS) {
      setState("failure");
      setError("Timed out waiting for the job to finish.");
      stop();
      return;
    }

    try {
      const supabase = createBrowserClient();
      const { data: { session } } = await supabase.auth.getSession();
      const token = session?.access_token ?? "";

      const res = await fetch(`${FASTAPI}/jobs/${jobId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });

      // An expired/invalid session won't recover by retrying — stop immediately.
      if (res.status === 401) {
        setState("failure");
        setError("Session expired — please sign in again.");
        stop();
        return;
      }

      if (!res.ok) {
        failuresRef.current += 1;
        if (failuresRef.current >= MAX_CONSECUTIVE_FAILURES) {
          setState("failure");
          setError("Lost contact with the job service.");
          stop();
        }
        return;
      }

      // Successful response — reset the consecutive-failure counter.
      failuresRef.current = 0;

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
      } else if (s === "unknown") {
        // Server can't find this job (never dispatched / expired). Terminal.
        setState("failure");
        setError(status.error ?? "Job not found.");
        stop();
      } else if (s === "started") {
        setState("started");
      }
    } catch {
      // Transient network error — count it toward the failure cap, then give up.
      failuresRef.current += 1;
      if (failuresRef.current >= MAX_CONSECUTIVE_FAILURES) {
        setState("failure");
        setError("Lost contact with the job service.");
        stop();
      }
    }
  }, [stop]);

  const start = useCallback((jobId: string) => {
    stop();
    jobIdRef.current = jobId;
    failuresRef.current = 0;
    pollsRef.current = 0;
    setState("pending");
    setResult(null);
    setError(null);
    intervalRef.current = setInterval(() => poll(jobId), POLL_MS);
  }, [poll, stop]);

  const reset = useCallback(() => {
    stop();
    failuresRef.current = 0;
    pollsRef.current = 0;
    setState("idle");
    setResult(null);
    setError(null);
    jobIdRef.current = null;
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  return { state, result, error, start, reset };
}
