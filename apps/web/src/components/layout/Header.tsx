"use client";

import { Search, Bell, Command, X, SlidersHorizontal } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";

interface HeaderProps {
  title: string;
  subtitle?: string;
}

type NotifEvent = {
  id: string;
  type: string | null;
  description: string | null;
  agent_name: string | null;
  severity: string;
  created_at: string;
};

// ─── Notification preference categories ───────────────────────────────────────

type PrefCategory = "contacts" | "deals" | "agents" | "email" | "system";

const PREF_CATEGORIES: { key: PrefCategory; label: string; types: string[] }[] = [
  { key: "contacts", label: "Contacts",     types: ["contact_created", "contact_updated", "contact_deleted"] },
  { key: "deals",    label: "Deals",        types: ["deal_moved", "deal_stage", "deal_created"]              },
  { key: "agents",   label: "Agent runs",   types: ["agent_run"]                                             },
  { key: "email",    label: "Email / Inbox", types: ["email_sent", "message_received"]                       },
  { key: "system",   label: "System",       types: [] /* catch-all */ },
]

const LS_LAST_READ_KEY = "crm_notif_last_read";
const LS_PREFS_KEY     = "crm_notif_prefs";

type NotifPrefs = Record<PrefCategory, boolean>;

const DEFAULT_PREFS: NotifPrefs = {
  contacts: true, deals: true, agents: true, email: true, system: true,
};

function loadPrefs(): NotifPrefs {
  try {
    const raw = localStorage.getItem(LS_PREFS_KEY);
    if (!raw) return { ...DEFAULT_PREFS };
    return { ...DEFAULT_PREFS, ...JSON.parse(raw) };
  } catch {
    return { ...DEFAULT_PREFS };
  }
}

function savePrefs(prefs: NotifPrefs) {
  try { localStorage.setItem(LS_PREFS_KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
}

function eventCategory(type: string | null): PrefCategory {
  if (!type) return "system";
  for (const cat of PREF_CATEGORIES) {
    if (cat.types.includes(type)) return cat.key;
  }
  return "system";
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

const severityDot: Record<string, string> = {
  info:    "bg-zinc-500",
  success: "bg-[#00C896]",
  warning: "bg-amber-400",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function Header({ title, subtitle }: HeaderProps) {
  const [searchFocused, setSearchFocused] = useState(false);
  const [notifOpen,     setNotifOpen]     = useState(false);
  const [prefsOpen,     setPrefsOpen]     = useState(false);
  const [events,        setEvents]        = useState<NotifEvent[]>([]);
  const [lastRead, setLastRead] = useState<number>(() => {
    try { return parseInt(localStorage.getItem(LS_LAST_READ_KEY) ?? "0", 10); } catch { return 0; }
  });
  const [prefs, setPrefs] = useState<NotifPrefs>(() => loadPrefs());
  const notifRef = useRef<HTMLDivElement>(null);

  // Fetch on first open
  useEffect(() => {
    if (!notifOpen || events.length > 0) return;
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      const workspaceId = (session.user.app_metadata?.workspace_id ?? session.user.user_metadata?.workspace_id) as string | undefined;
      if (!workspaceId) return;
      apiClient.listActivity(workspaceId, session.access_token, { limit: 20 })
        .then((data) => { if (Array.isArray(data)) setEvents(data as NotifEvent[]); })
        .catch(() => {});
    });
  }, [notifOpen, events.length]);

  // Close on outside click
  useEffect(() => {
    if (!notifOpen) return;
    const handler = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
        setPrefsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [notifOpen]);

  const handleMarkAllRead = () => {
    const now = Date.now();
    setLastRead(now);
    try { localStorage.setItem(LS_LAST_READ_KEY, String(now)); } catch { /* ignore */ }
  };

  const togglePref = (key: PrefCategory) => {
    const next = { ...prefs, [key]: !prefs[key] };
    setPrefs(next);
    savePrefs(next);
  };

  // Apply pref filter
  const visibleEvents = events.filter(ev => prefs[eventCategory(ev.type)]);

  const unreadCount = visibleEvents.filter(
    (ev) => new Date(ev.created_at).getTime() > lastRead
  ).length;
  const badgeCount = notifOpen ? 0 : unreadCount;

  // How many categories are disabled (shown in gear badge)
  const disabledCount = Object.values(prefs).filter(v => !v).length;

  return (
    <header className="sticky top-14 md:top-0 z-20 flex items-center gap-2 sm:gap-4 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-xl px-4 md:px-6 py-3 md:py-4">
      {/* Page title */}
      <div className="flex-1 min-w-0">
        <h1 className="text-base sm:text-lg font-semibold text-zinc-100 truncate">{title}</h1>
        {subtitle && (
          <p className="text-xs text-zinc-500 mt-0.5 truncate font-mono">{subtitle}</p>
        )}
      </div>

      {/* Search bar — hidden on smallest screens */}
      <div
        className={cn(
          "relative hidden sm:flex items-center gap-2 rounded-xl border bg-zinc-900 px-3 py-2 transition-all duration-200 w-44 lg:w-64",
          searchFocused ? "border-indigo-500/50 shadow-glow-sm" : "border-zinc-800"
        )}
      >
        <Search className="h-3.5 w-3.5 text-zinc-500 flex-shrink-0" aria-hidden="true" />
        <input
          type="search"
          placeholder="Search contacts, deals..."
          className="flex-1 bg-transparent text-sm text-zinc-300 placeholder-zinc-600 outline-none min-w-0"
          onFocus={() => setSearchFocused(true)}
          onBlur={() => setSearchFocused(false)}
          aria-label="Search contacts, deals, and agents"
        />
        <kbd className="hidden sm:flex items-center gap-0.5 rounded border border-zinc-700 bg-zinc-800 px-1.5 py-0.5 text-[10px] font-mono text-zinc-500">
          <Command className="h-2.5 w-2.5" aria-hidden="true" />K
        </kbd>
      </div>

      {/* Notifications */}
      <div ref={notifRef} className="relative">
        <button
          onClick={() => { setNotifOpen((v) => !v); setPrefsOpen(false); }}
          className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-100 hover:border-zinc-700 transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950"
          aria-label="Notifications"
          aria-expanded={notifOpen}
        >
          <Bell className="h-4 w-4" aria-hidden="true" />
          {badgeCount > 0 && (
            <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-indigo-600 text-[9px] font-bold text-white">
              {badgeCount > 9 ? "9+" : badgeCount}
            </span>
          )}
        </button>

        {notifOpen && (
          <div className="absolute right-0 top-full mt-2 w-80 rounded-xl border border-zinc-800 bg-zinc-900 shadow-2xl overflow-hidden z-50">

            {/* Header row */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
              <p className="text-sm font-semibold text-zinc-100">
                {prefsOpen ? "Notification filters" : "Activity"}
              </p>
              <div className="flex items-center gap-2">
                {!prefsOpen && unreadCount > 0 && (
                  <button
                    onClick={handleMarkAllRead}
                    className="text-[10px] font-medium text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer"
                    aria-label="Mark all notifications as read"
                  >
                    Mark all read
                  </button>
                )}
                {/* Filter toggle */}
                <button
                  onClick={() => setPrefsOpen(v => !v)}
                  className={cn(
                    "relative flex h-6 w-6 items-center justify-center rounded-md transition-colors cursor-pointer",
                    prefsOpen ? "bg-indigo-600/20 text-indigo-400" : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800"
                  )}
                  aria-label="Toggle notification filters"
                  aria-pressed={prefsOpen}
                >
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                  {disabledCount > 0 && !prefsOpen && (
                    <span className="absolute -top-0.5 -right-0.5 flex h-2.5 w-2.5 items-center justify-center rounded-full bg-amber-500 text-[7px] font-bold text-white leading-none">
                      {disabledCount}
                    </span>
                  )}
                </button>
                <button
                  onClick={() => { setNotifOpen(false); setPrefsOpen(false); }}
                  className="text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
                  aria-label="Close notifications"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            {/* Preferences pane */}
            {prefsOpen ? (
              <div className="px-4 py-3 space-y-0.5">
                <p className="text-[10px] font-mono text-zinc-600 uppercase tracking-widest mb-2">
                  Show notifications for
                </p>
                {PREF_CATEGORIES.map(({ key, label }) => (
                  <label
                    key={key}
                    className="flex items-center justify-between py-2 px-1 rounded-lg hover:bg-zinc-800/40 cursor-pointer transition-colors"
                  >
                    <span className={cn("text-sm", prefs[key] ? "text-zinc-200" : "text-zinc-500")}>
                      {label}
                    </span>
                    <div
                      role="switch"
                      aria-checked={prefs[key]}
                      onClick={() => togglePref(key)}
                      className={cn(
                        "relative h-5 w-9 rounded-full transition-colors shrink-0",
                        prefs[key] ? "bg-indigo-600" : "bg-zinc-700"
                      )}
                    >
                      <span
                        className={cn(
                          "absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all shadow-sm",
                          prefs[key] ? "left-[18px]" : "left-0.5"
                        )}
                      />
                    </div>
                  </label>
                ))}
                <p className="text-[10px] text-zinc-600 font-mono pt-2 pb-1">
                  Preferences saved automatically
                </p>
              </div>
            ) : (
              /* Events list */
              <div className="max-h-80 overflow-y-auto divide-y divide-zinc-800/50">
                {visibleEvents.length === 0 ? (
                  <div className="px-4 py-6 text-center text-sm text-zinc-500">
                    {events.length > 0
                      ? "All event types are filtered out"
                      : "No recent activity"}
                  </div>
                ) : (
                  visibleEvents.map((ev) => {
                    const isUnread = new Date(ev.created_at).getTime() > lastRead;
                    return (
                      <div
                        key={ev.id}
                        className={cn(
                          "flex items-start gap-3 px-4 py-3 hover:bg-zinc-800/30 transition-colors",
                          isUnread && "bg-indigo-600/5"
                        )}
                      >
                        <span className={cn("mt-1.5 h-1.5 w-1.5 rounded-full shrink-0", severityDot[ev.severity] ?? "bg-zinc-500")} />
                        <div className="flex-1 min-w-0">
                          <p className={cn("text-xs leading-snug truncate", isUnread ? "text-zinc-200 font-medium" : "text-zinc-300")}>
                            {ev.description ?? ""}
                          </p>
                          <p className="text-[10px] text-zinc-600 font-mono mt-0.5">
                            {ev.agent_name ?? "System"} · {timeAgo(ev.created_at)}
                          </p>
                        </div>
                        {isUnread && <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-indigo-500 shrink-0" />}
                      </div>
                    );
                  })
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </header>
  );
}
