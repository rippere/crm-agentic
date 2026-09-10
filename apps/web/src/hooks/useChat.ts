"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";
import { isDemoMode } from "@/lib/demo-mode";
import { demoChatMessages, demoDiscoveryRun } from "@/lib/demo-data";
import { useJobPoller } from "@/hooks/useJobPoller";

// ─── Types ───────────────────────────────────────────────────────────────────
// Mirrors the API's ai.py ChatMessage / ChatResponse (Inc 1, §2.1.9). Kept local
// to the hook so api-client can stay import-cycle-free.

export type ChatRole = "user" | "assistant" | "system";

export interface ChatMessage {
  role: ChatRole;
  content: string;
  /** Client-only flag so the panel can style system/completion lines distinctly. */
  kind?: "message" | "status" | "error";
}

/** Custom event fired when a discovery run finishes, so the /leads surface can
 *  refetch the freshly-discovered rows. The leads hook/page can listen for it;
 *  it is a no-op if nothing is mounted. */
export const DISCOVERY_COMPLETE_EVENT = "novacrm:discovery-complete";

async function getAuth() {
  const supabase = createBrowserClient();
  const { data: { session } } = await supabase.auth.getSession();
  const token = session?.access_token;
  const workspaceId = (session?.user?.app_metadata?.workspace_id ?? session?.user?.user_metadata?.workspace_id) as string | undefined;
  return { token, workspaceId };
}

function completionLine(found: unknown, inserted: unknown, locality: unknown): string {
  const f = typeof found === "number" ? found : Number(found ?? 0);
  const i = typeof inserted === "number" ? inserted : Number(inserted ?? 0);
  const where = typeof locality === "string" && locality ? ` in ${locality}` : "";
  return `Found ${f} venues${where}, ${i} loaded to Leads.`;
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(
    isDemoMode ? (demoChatMessages as ChatMessage[]) : [],
  );
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The action name awaiting operator approval (fail-closed authority clamped it
  // to `ask` — R11/R12). Null when nothing is pending.
  const [needsConfirmation, setNeedsConfirmation] = useState<string | null>(null);
  // Demo mode has no /jobs backend, so a discovery "job" is simulated locally.
  const [demoRunning, setDemoRunning] = useState(false);

  const poller = useJobPoller();
  const { state: jobState, result: jobResult, error: jobError, start: startJob, reset: resetJob } = poller;

  const demoTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const appendMessage = useCallback((msg: ChatMessage) => {
    setMessages((prev) => [...prev, msg]);
  }, []);

  // ── Real job (non-demo): render the completion line from the R2 summary keys
  //    {found, inserted, locality} and signal /leads to refetch. ──
  useEffect(() => {
    if (jobState === "success") {
      const r = jobResult ?? {};
      appendMessage({
        role: "assistant",
        kind: "status",
        content: completionLine(r.found, r.inserted, r.locality),
      });
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(DISCOVERY_COMPLETE_EVENT, { detail: r }));
      }
      resetJob();
    } else if (jobState === "failure") {
      appendMessage({
        role: "assistant",
        kind: "error",
        content: jobError ?? "The discovery run failed. Please try again.",
      });
      resetJob();
    }
  }, [jobState, jobResult, jobError, appendMessage, resetJob]);

  // Clean up any pending demo timer on unmount.
  useEffect(() => () => {
    if (demoTimerRef.current) clearTimeout(demoTimerRef.current);
  }, []);

  const simulateDemoJob = useCallback(() => {
    setDemoRunning(true);
    demoTimerRef.current = setTimeout(() => {
      const { found, inserted } = demoDiscoveryRun.stats;
      appendMessage({
        role: "assistant",
        kind: "status",
        content: completionLine(found, inserted, demoDiscoveryRun.locality),
      });
      setDemoRunning(false);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent(DISCOVERY_COMPLETE_EVENT, { detail: demoDiscoveryRun.stats }));
      }
    }, 1600);
  }, [appendMessage]);

  /**
   * Send a chat turn. `text` is appended as the user's message; `confirm` names an
   * actuating action the operator is approving (re-sent after a needs_confirmation
   * clamp). On a returned job_id the poller drives progress and the completion line.
   */
  const sendMessage = useCallback(async (text: string, confirm?: string) => {
    const trimmed = text.trim();
    if (!trimmed || sending) return;

    setNeedsConfirmation(null);
    setError(null);
    setSending(true);

    const userMsg: ChatMessage = { role: "user", content: trimmed };
    const transcript = [...messages, userMsg];
    setMessages(transcript);

    try {
      const { token, workspaceId } = await getAuth();
      if (!isDemoMode && (!token || !workspaceId)) {
        throw new Error("Not authenticated");
      }
      const res = await apiClient.aiChat(
        workspaceId ?? "demo-workspace-1",
        transcript.map((m) => ({ role: m.role, content: m.content })),
        confirm ?? null,
        token ?? "",
      );

      if (res.answer) {
        appendMessage({ role: "assistant", content: res.answer });
      }

      if (res.needs_confirmation) {
        setNeedsConfirmation(res.pending_action ?? "discovery");
      }

      if (res.job_id) {
        if (isDemoMode || res.job_id.startsWith("demo")) {
          simulateDemoJob();
        } else {
          startJob(res.job_id);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSending(false);
    }
  }, [messages, sending, appendMessage, simulateDemoJob, startJob]);

  const reset = useCallback(() => {
    if (demoTimerRef.current) clearTimeout(demoTimerRef.current);
    resetJob();
    setDemoRunning(false);
    setNeedsConfirmation(null);
    setError(null);
    setSending(false);
    setMessages(isDemoMode ? (demoChatMessages as ChatMessage[]) : []);
  }, [resetJob]);

  // A long-running discovery job is in flight (real poller or demo simulation).
  const running = demoRunning || jobState === "pending" || jobState === "started";

  return {
    messages,
    sendMessage,
    sending,
    running,
    error,
    needsConfirmation,
    reset,
  };
}
