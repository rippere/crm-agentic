"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { useChat, type ChatMessage } from "@/hooks/useChat";
import {
  Sparkles, Send, Loader2, CheckCircle2, AlertCircle, User, ArrowRight,
} from "lucide-react";

// Suggested prompts to seed the operator's first turn.
const SUGGESTIONS = [
  "Find photo-booth leads in Burlington, VT",
  "Discover event venues near me",
  "What's happening in my pipeline?",
];

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === "user";

  if (msg.kind === "status") {
    return (
      <div className="flex items-start gap-2.5 px-1">
        <CheckCircle2 className="h-4 w-4 shrink-0 text-[#00C896] mt-0.5" aria-hidden="true" />
        <p className="text-sm text-[#00C896] font-medium leading-relaxed">
          {msg.content}{" "}
          <Link href="/leads?source=discovery" className="underline underline-offset-2 hover:text-[#00C896]/80">
            View in Leads
          </Link>
        </p>
      </div>
    );
  }

  if (msg.kind === "error") {
    return (
      <div className="flex items-start gap-2.5 px-1" role="alert">
        <AlertCircle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" aria-hidden="true" />
        <p className="text-sm text-red-400 leading-relaxed">{msg.content}</p>
      </div>
    );
  }

  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isUser
            ? "bg-zinc-800 text-zinc-300"
            : "bg-indigo-600 text-white",
        )}
        style={isUser ? undefined : { boxShadow: "0 0 12px rgba(99,102,241,0.4)" }}
        aria-hidden="true"
      >
        {isUser ? <User className="h-3.5 w-3.5" /> : <Sparkles className="h-3.5 w-3.5" />}
      </div>
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap",
          isUser
            ? "bg-zinc-800 text-zinc-100 rounded-tr-sm"
            : "bg-zinc-900 border border-zinc-800 text-zinc-200 rounded-tl-sm",
        )}
      >
        {msg.content}
      </div>
    </div>
  );
}

export default function ChatPanel() {
  const { messages, sendMessage, sending, running, error, needsConfirmation, reset } = useChat();
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to the newest message / status line.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, running]);

  const handleSend = () => {
    const text = input;
    if (!text.trim() || sending) return;
    setInput("");
    void sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleConfirm = () => {
    if (!needsConfirmation || sending) return;
    void sendMessage("Yes — go ahead and run it.", needsConfirmation);
  };

  return (
    <div className="flex flex-col flex-1 min-h-0 rounded-2xl border border-zinc-800 bg-zinc-950 overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3 shrink-0">
        <div className="flex items-center gap-2.5">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600"
            style={{ boxShadow: "0 0 14px rgba(99,102,241,0.45)" }}
          >
            <Sparkles className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
          <div>
            <p className="text-sm font-semibold text-zinc-100 leading-none">Nova — Lead Engine</p>
            <p className="text-[11px] text-zinc-500 mt-1">Ask me to discover, score, and load leads</p>
          </div>
        </div>
        <button
          onClick={reset}
          className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer px-2 py-1 rounded-md hover:bg-zinc-800/50"
        >
          New chat
        </button>
      </div>

      {/* Message stream */}
      <div ref={scrollRef} className="flex-1 min-h-0 overflow-y-auto px-4 py-5 space-y-5" aria-live="polite">
        {messages.map((msg, i) => (
          <MessageBubble key={i} msg={msg} />
        ))}

        {/* Running-job indicator */}
        {running && (
          <div className="flex items-center gap-2.5 px-1 text-sm text-zinc-400">
            <Loader2 className="h-4 w-4 animate-spin text-indigo-400" aria-hidden="true" />
            <span>Scanning the market and scoring venues…</span>
          </div>
        )}

        {/* Confirm gate (fail-closed authority — operator approval required) */}
        {needsConfirmation && !running && (
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-indigo-500/30 bg-indigo-500/5 px-4 py-3">
            <p className="text-sm text-zinc-300 flex-1 min-w-[180px]">
              This action spends on live APIs and needs your approval.
            </p>
            <button
              onClick={handleConfirm}
              disabled={sending}
              className="inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white hover:bg-indigo-500 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              Confirm &amp; run
              <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        )}

        {/* Send error */}
        {error && (
          <div className="flex items-start gap-2.5 px-1" role="alert">
            <AlertCircle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" aria-hidden="true" />
            <p className="text-sm text-red-400 leading-relaxed">{error}</p>
          </div>
        )}
      </div>

      {/* Suggestions (only before the operator's first turn) */}
      {messages.filter((m) => m.role === "user").length === 0 && (
        <div className="flex flex-wrap gap-2 px-4 pb-3 shrink-0">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => { setInput(""); void sendMessage(s); }}
              disabled={sending || running}
              className="rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 hover:border-zinc-700 transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Composer */}
      <div className="border-t border-zinc-800 p-3 shrink-0">
        <div className="flex items-end gap-2 rounded-xl border border-zinc-800 bg-zinc-900 px-3 py-2 focus-within:border-indigo-500/50 transition-colors">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Nova to find leads…"
            rows={1}
            className="flex-1 resize-none bg-transparent text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none max-h-32 py-1"
            aria-label="Message Nova"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
            aria-label="Send message"
          >
            {sending ? <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> : <Send className="h-4 w-4" aria-hidden="true" />}
          </button>
        </div>
      </div>
    </div>
  );
}
