"use client";

import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  Search, X, Brain, Mail, ClipboardList, Plus, Sparkles,
  Loader2, ArrowUp, KanbanSquare, CheckSquare, ChevronRight, Users,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { createBrowserClient } from "@/lib/supabase";

// ─── Types ────────────────────────────────────────────────────────────────────

type SearchContact = { id: string; name: string; email: string; company: string; role: string; status: string }
type SearchDeal    = { id: string; title: string; company: string; value: number; stage: string }
type SearchTask    = { id: string; title: string; status: string; due_date: string | null; contact_id: string | null }

type ResultItem =
  | { kind: "contact"; data: SearchContact }
  | { kind: "deal";    data: SearchDeal    }
  | { kind: "task";    data: SearchTask    }

type SearchResults = { contacts: SearchContact[]; deals: SearchDeal[]; tasks: SearchTask[] }

// ─── Constants ────────────────────────────────────────────────────────────────

const STAGE_LABELS: Record<string, string> = {
  lead: "Lead", discovery: "Discovery", proposal: "Proposal",
  negotiation: "Negotiation", closed_won: "Won", closed_lost: "Lost",
}

const STATUS_COLORS: Record<string, string> = {
  hot: "text-red-400", warm: "text-amber-400", cold: "text-blue-400",
  lead: "text-zinc-400", customer: "text-emerald-400", prospect: "text-indigo-400",
}

const AI_CHIPS = [
  { icon: <Brain className="h-3.5 w-3.5" />,       label: "Summarize pipeline"   },
  { icon: <Mail className="h-3.5 w-3.5" />,         label: "Draft follow-up for"  },
  { icon: <ClipboardList className="h-3.5 w-3.5" />, label: "What's stale?"       },
  { icon: <Plus className="h-3.5 w-3.5" />,          label: "New deal ideas"      },
  { icon: <Sparkles className="h-3.5 w-3.5" />,      label: "Top leads this week" },
]

// ─── Debounce hook ────────────────────────────────────────────────────────────

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

// ─── Component ────────────────────────────────────────────────────────────────

interface CommandPaletteProps {
  onClose: () => void;
  onSubmit?: (value: string) => void;
}

export default function CommandPalette({ onClose }: CommandPaletteProps) {
  const router = useRouter()
  const inputRef    = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const [mode,       setMode]       = useState<"search" | "ai">("search")
  const [query,      setQuery]      = useState("")
  const [aiValue,    setAiValue]    = useState("")
  const [searching,  setSearching]  = useState(false)
  const [results,    setResults]    = useState<SearchResults | null>(null)
  const [activeIdx,  setActiveIdx]  = useState(-1)
  const [aiLoading,  setAiLoading]  = useState(false)
  const [aiAnswer,   setAiAnswer]   = useState<string | null>(null)

  const debouncedQuery = useDebounce(query, 280)

  // Flat navigable list derived from grouped results
  const flatResults = useMemo<ResultItem[]>(() => {
    if (!results) return []
    return [
      ...results.contacts.map(d => ({ kind: "contact" as const, data: d })),
      ...results.deals   .map(d => ({ kind: "deal"    as const, data: d })),
      ...results.tasks   .map(d => ({ kind: "task"    as const, data: d })),
    ]
  }, [results])

  // Focus the right input when mode changes
  useEffect(() => {
    if (mode === "search") inputRef.current?.focus()
    else                   textareaRef.current?.focus()
  }, [mode])

  // ESC closes
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", h)
    return () => document.removeEventListener("keydown", h)
  }, [onClose])

  // Search on debounced query
  useEffect(() => {
    if (!debouncedQuery || debouncedQuery.length < 2) {
      setResults(null)
      setActiveIdx(-1)
      return
    }
    let cancelled = false
    setSearching(true)

    const supabase = createBrowserClient()
    supabase.auth.getSession().then(({ data: { session } }) => {
      const token       = session?.access_token                         ?? "demo-token"
      const workspaceId = session?.user?.user_metadata?.workspace_id   ?? "demo-workspace-1"
      apiClient.globalSearch(workspaceId, debouncedQuery, token)
        .then(data => { if (!cancelled) { setResults(data); setActiveIdx(-1) } })
        .catch(() => { if (!cancelled) setResults({ contacts: [], deals: [], tasks: [] }) })
        .finally(() => { if (!cancelled) setSearching(false) })
    })
    return () => { cancelled = true }
  }, [debouncedQuery])

  const navigateTo = useCallback((item: ResultItem) => {
    onClose()
    if      (item.kind === "contact") router.push(`/contacts/${item.data.id}`)
    else if (item.kind === "deal")    router.push(`/pipeline/${item.data.id}`)
    else                              router.push("/tasks")
  }, [router, onClose])

  // Arrow-key + Enter navigation in search mode
  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (flatResults.length === 0) return
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setActiveIdx(i => Math.min(i + 1, flatResults.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActiveIdx(i => Math.max(i - 1, -1))
    } else if (e.key === "Enter" && activeIdx >= 0) {
      e.preventDefault()
      navigateTo(flatResults[activeIdx])
    }
  }

  // AI submit
  const handleAiKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAiSubmit() }
  }
  const handleAiSubmit = async () => {
    if (!aiValue.trim() || aiLoading) return
    setAiLoading(true)
    setAiAnswer(null)
    try {
      const supabase = createBrowserClient()
      const { data: { session } } = await supabase.auth.getSession()
      const token       = session?.access_token                        ?? "demo-token"
      const workspaceId = session?.user?.user_metadata?.workspace_id  ?? "demo-workspace-1"
      const result = await apiClient.aiQuery(workspaceId, aiValue.trim(), token)
      setAiAnswer(result?.answer ?? "No response.")
    } catch {
      setAiAnswer("Nova is unavailable right now. Check that ANTHROPIC_API_KEY is configured.")
    } finally {
      setAiLoading(false)
    }
  }

  const hasQuery    = query.length >= 2
  const totalCount  = flatResults.length

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/80 backdrop-blur-sm p-4 pt-[10vh]"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-2xl border border-zinc-700/60 bg-zinc-900 shadow-[0_0_60px_rgba(99,102,241,0.15)] overflow-hidden"
        onClick={e => e.stopPropagation()}
        role="dialog"
        aria-label="Command palette"
      >
        {/* Mode tabs */}
        <div className="flex items-center gap-1.5 px-3 pt-3 pb-2 border-b border-zinc-800">
          <button
            onClick={() => setMode("search")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer",
              mode === "search" ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:text-zinc-300"
            )}
          >
            <Search className="h-3.5 w-3.5" /> Search
          </button>
          <button
            onClick={() => setMode("ai")}
            className={cn(
              "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer",
              mode === "ai"
                ? "bg-indigo-600/20 text-indigo-300 border border-indigo-500/30"
                : "text-zinc-500 hover:text-zinc-300"
            )}
          >
            <Sparkles className="h-3.5 w-3.5" /> Nova AI
          </button>
          <div className="flex-1" />
          <button
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-lg text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 transition-colors cursor-pointer"
            aria-label="Close command palette"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* ── SEARCH MODE ──────────────────────────────────────────────────── */}
        {mode === "search" && (
          <>
            {/* Input */}
            <div className="flex items-center gap-3 px-4 py-3">
              {searching
                ? <Loader2 className="h-4 w-4 shrink-0 text-indigo-400 animate-spin" aria-hidden />
                : <Search  className="h-4 w-4 shrink-0 text-zinc-500" aria-hidden />
              }
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                placeholder="Search contacts, deals, tasks…"
                className="flex-1 bg-transparent text-zinc-100 text-sm placeholder:text-zinc-600 outline-none"
                aria-label="Search"
                aria-autocomplete="list"
                aria-expanded={results !== null}
              />
              {query && (
                <button
                  onClick={() => { setQuery(""); setResults(null); inputRef.current?.focus() }}
                  className="text-zinc-600 hover:text-zinc-400 cursor-pointer transition-colors"
                  aria-label="Clear search"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Results */}
            {hasQuery && (
              <div className="max-h-[420px] overflow-y-auto border-t border-zinc-800" role="listbox">
                {results && totalCount === 0 && (
                  <div className="px-4 py-8 text-center text-sm text-zinc-500">
                    No results for{" "}
                    <span className="text-zinc-300 font-medium">"{query}"</span>
                  </div>
                )}

                {results && (
                  <div className="py-1.5">
                    {/* Contacts */}
                    {results.contacts.length > 0 && (
                      <section aria-label="Contacts">
                        <p className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-zinc-600 font-mono">
                          Contacts ({results.contacts.length})
                        </p>
                        {results.contacts.map(c => {
                          const idx = flatResults.findIndex(r => r.kind === "contact" && r.data.id === c.id)
                          return (
                            <button
                              key={c.id}
                              role="option"
                              aria-selected={activeIdx === idx}
                              onClick={() => navigateTo({ kind: "contact", data: c })}
                              onMouseEnter={() => setActiveIdx(idx)}
                              className={cn(
                                "w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors cursor-pointer",
                                activeIdx === idx ? "bg-indigo-600/10" : "hover:bg-zinc-800/40"
                              )}
                            >
                              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-zinc-800 border border-zinc-700 text-[10px] font-semibold text-zinc-400 font-mono">
                                {c.name.slice(0, 2).toUpperCase()}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-zinc-200 truncate">{c.name}</p>
                                <p className="text-xs text-zinc-500 truncate">
                                  {c.company}{c.role ? ` · ${c.role}` : ""}
                                </p>
                              </div>
                              <span className={cn("text-[10px] font-mono shrink-0 capitalize", STATUS_COLORS[c.status] ?? "text-zinc-500")}>
                                {c.status}
                              </span>
                              <ChevronRight className="h-3.5 w-3.5 text-zinc-700 shrink-0" />
                            </button>
                          )
                        })}
                      </section>
                    )}

                    {/* Deals */}
                    {results.deals.length > 0 && (
                      <section aria-label="Deals">
                        <p className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-zinc-600 font-mono">
                          Deals ({results.deals.length})
                        </p>
                        {results.deals.map(d => {
                          const idx = flatResults.findIndex(r => r.kind === "deal" && r.data.id === d.id)
                          return (
                            <button
                              key={d.id}
                              role="option"
                              aria-selected={activeIdx === idx}
                              onClick={() => navigateTo({ kind: "deal", data: d })}
                              onMouseEnter={() => setActiveIdx(idx)}
                              className={cn(
                                "w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors cursor-pointer",
                                activeIdx === idx ? "bg-indigo-600/10" : "hover:bg-zinc-800/40"
                              )}
                            >
                              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-zinc-800 border border-zinc-700">
                                <KanbanSquare className="h-3.5 w-3.5 text-zinc-400" aria-hidden />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-zinc-200 truncate">{d.title}</p>
                                <p className="text-xs text-zinc-500 truncate">{d.company}</p>
                              </div>
                              <div className="text-right shrink-0">
                                <p className="text-xs font-mono text-zinc-300">${d.value.toLocaleString()}</p>
                                <p className="text-[10px] text-zinc-600">{STAGE_LABELS[d.stage] ?? d.stage}</p>
                              </div>
                              <ChevronRight className="h-3.5 w-3.5 text-zinc-700 shrink-0" />
                            </button>
                          )
                        })}
                      </section>
                    )}

                    {/* Tasks */}
                    {results.tasks.length > 0 && (
                      <section aria-label="Tasks">
                        <p className="px-4 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-zinc-600 font-mono">
                          Tasks ({results.tasks.length})
                        </p>
                        {results.tasks.map(t => {
                          const idx = flatResults.findIndex(r => r.kind === "task" && r.data.id === t.id)
                          return (
                            <button
                              key={t.id}
                              role="option"
                              aria-selected={activeIdx === idx}
                              onClick={() => navigateTo({ kind: "task", data: t })}
                              onMouseEnter={() => setActiveIdx(idx)}
                              className={cn(
                                "w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors cursor-pointer",
                                activeIdx === idx ? "bg-indigo-600/10" : "hover:bg-zinc-800/40"
                              )}
                            >
                              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-zinc-800 border border-zinc-700">
                                <CheckSquare className="h-3.5 w-3.5 text-zinc-400" aria-hidden />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-zinc-200 truncate">{t.title}</p>
                                <p className="text-xs text-zinc-500">
                                  {t.due_date ? `Due ${t.due_date}` : "No due date"} · {t.status}
                                </p>
                              </div>
                              <ChevronRight className="h-3.5 w-3.5 text-zinc-700 shrink-0" />
                            </button>
                          )
                        })}
                      </section>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Empty-state hint */}
            {!hasQuery && (
              <div className="px-4 py-6 text-center">
                <p className="text-xs text-zinc-600 font-mono">Type at least 2 characters to search…</p>
                <div className="flex items-center justify-center gap-4 mt-3">
                  <span className="flex items-center gap-1.5 text-[11px] text-zinc-700 font-mono">
                    <Users className="h-3 w-3" /> contacts
                  </span>
                  <span className="text-zinc-800">·</span>
                  <span className="flex items-center gap-1.5 text-[11px] text-zinc-700 font-mono">
                    <KanbanSquare className="h-3 w-3" /> deals
                  </span>
                  <span className="text-zinc-800">·</span>
                  <span className="flex items-center gap-1.5 text-[11px] text-zinc-700 font-mono">
                    <CheckSquare className="h-3 w-3" /> tasks
                  </span>
                </div>
              </div>
            )}
          </>
        )}

        {/* ── AI MODE ──────────────────────────────────────────────────────── */}
        {mode === "ai" && (
          <>
            <div className="px-4 py-3">
              <div className="relative rounded-xl border border-zinc-700/60 bg-zinc-900/60">
                <textarea
                  ref={textareaRef}
                  value={aiValue}
                  onChange={e => { setAiValue(e.target.value); setAiAnswer(null) }}
                  onKeyDown={handleAiKeyDown}
                  placeholder="Ask anything about your deals, contacts, or pipeline…"
                  rows={3}
                  className="w-full px-4 py-3 resize-none bg-transparent border-none outline-none text-zinc-100 text-sm leading-relaxed placeholder:text-zinc-600"
                />
                <div className="flex items-center justify-between px-3 pb-3 pt-1">
                  <div className="flex items-center gap-1.5">
                    <div className="h-1.5 w-1.5 rounded-full bg-[#00C896] agent-pulse" />
                    <span className="text-[10px] font-mono text-zinc-600">Nova AI</span>
                  </div>
                  <button
                    onClick={handleAiSubmit}
                    disabled={!aiValue.trim() || aiLoading}
                    className={cn(
                      "flex items-center justify-center h-7 w-7 rounded-lg transition-all",
                      aiValue.trim() && !aiLoading
                        ? "bg-indigo-600 hover:bg-indigo-500 text-white cursor-pointer shadow-[0_0_12px_rgba(99,102,241,0.4)]"
                        : "bg-zinc-800 text-zinc-600 cursor-not-allowed"
                    )}
                    aria-label="Send to Nova AI"
                  >
                    {aiLoading
                      ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      : <ArrowUp className="h-3.5 w-3.5" />
                    }
                  </button>
                </div>

                {/* AI response */}
                {(aiLoading || aiAnswer) && (
                  <div className="border-t border-zinc-800 px-4 py-3">
                    {aiLoading ? (
                      <div className="flex items-center gap-2 text-xs text-zinc-500">
                        <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />
                        Nova is thinking…
                      </div>
                    ) : aiAnswer ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-1.5 rounded-full bg-[#00C896]" />
                          <span className="text-[10px] font-mono font-semibold text-[#00C896] tracking-widest">NOVA</span>
                        </div>
                        <p className="text-sm text-zinc-200 leading-relaxed">{aiAnswer}</p>
                        <button
                          onClick={() => { setAiValue(""); setAiAnswer(null); textareaRef.current?.focus() }}
                          className="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors font-mono cursor-pointer"
                        >
                          Ask another →
                        </button>
                      </div>
                    ) : null}
                  </div>
                )}
              </div>
            </div>

            {/* AI chips */}
            {!aiAnswer && (
              <div className="flex flex-wrap gap-2 px-4 pb-4">
                {AI_CHIPS.map(({ icon, label }) => (
                  <button
                    key={label}
                    onClick={() => { setAiValue(label + " "); setAiAnswer(null); textareaRef.current?.focus() }}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800/60 hover:bg-zinc-800 rounded-full border border-zinc-700/60 hover:border-zinc-700 text-zinc-400 hover:text-zinc-200 transition-all text-xs font-medium cursor-pointer"
                  >
                    <span className="text-indigo-400">{icon}</span>
                    {label}
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        {/* Footer */}
        <div className="flex items-center gap-2.5 px-4 py-2.5 border-t border-zinc-800/50 bg-zinc-950/40">
          {mode === "search" && totalCount > 0 && (
            <>
              <span className="text-[10px] font-mono text-zinc-700">↑↓ navigate</span>
              <span className="text-zinc-800">·</span>
              <span className="text-[10px] font-mono text-zinc-700">↩ open</span>
              <span className="text-zinc-800">·</span>
            </>
          )}
          <span className="text-[10px] font-mono text-zinc-700">
            <kbd className="px-1 rounded border border-zinc-800 bg-zinc-900 text-zinc-700">⌘K</kbd> toggle
          </span>
          <span className="text-zinc-800">·</span>
          <span className="text-[10px] font-mono text-zinc-700">
            <kbd className="px-1 rounded border border-zinc-800 bg-zinc-900 text-zinc-700">ESC</kbd> close
          </span>
        </div>
      </div>
    </div>
  )
}
