"use client";

import { Search, Bell, Command, X } from "lucide-react";
import { useState, useEffect, useRef } from "react";
import { cn } from "@/lib/utils";
import { createBrowserClient } from "@/lib/supabase";
import { apiClient } from "@/lib/api-client";

interface HeaderProps {
  title: string;
  subtitle?: string;
}

type NotifEvent = { id: string; description: string; agent_name: string; severity: string; created_at: string };

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

const LS_LAST_READ_KEY = "crm_notif_last_read";

export default function Header({ title, subtitle }: HeaderProps) {
  const [searchFocused, setSearchFocused] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [events, setEvents] = useState<NotifEvent[]>([]);
  const [lastRead, setLastRead] = useState<number>(() => {
    try { return parseInt(localStorage.getItem(LS_LAST_READ_KEY) ?? "0", 10); } catch { return 0; }
  });
  const notifRef = useRef<HTMLDivElement>(null);

  // Fetch on first open
  useEffect(() => {
    if (!notifOpen || events.length > 0) return;
    const supabase = createBrowserClient();
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) return;
      const workspaceId = session.user.user_metadata?.workspace_id as string | undefined;
      if (!workspaceId) return;
      apiClient.listActivity(workspaceId, session.access_token, { limit: 8 })
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

  const unreadCount = events.filter(
    (ev) => new Date(ev.created_at).getTime() > lastRead
  ).length;
  const badgeCount = notifOpen ? 0 : unreadCount;

  return (
    <header className="sticky top-14 md:top-0 z-20 flex items-center gap-2 sm:gap-4 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-xl px-4 md:px-6 py-3 md:py-4">
      {/* Page title */}
      <div className="flex-1 min-w-0">
        <h1 className="text-base sm:text-lg font-semibold text-zinc-100 truncate">{title}</h1>
        {subtitle && (
          <p className="text-xs text-zinc-500 mt-0.5 truncate font-mono">{subtitle}</p>
        )}
      </div>

      {/* Search bar — hidden on the smallest screens to avoid crowding the title */}
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
          onClick={() => setNotifOpen((v) => !v)}
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
            <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
              <p className="text-sm font-semibold text-zinc-100">Activity</p>
              <div className="flex items-center gap-2">
                {unreadCount > 0 && (
                  <button
                    onClick={handleMarkAllRead}
                    className="text-[10px] font-medium text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer"
                    aria-label="Mark all notifications as read"
                  >
                    Mark all read
                  </button>
                )}
                <button
                  onClick={() => setNotifOpen(false)}
                  className="text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
                  aria-label="Close notifications"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="max-h-80 overflow-y-auto divide-y divide-zinc-800/50">
              {events.length === 0 ? (
                <div className="px-4 py-6 text-center text-sm text-zinc-500">
                  No recent activity
                </div>
              ) : (
                events.map((ev) => {
                  const isUnread = new Date(ev.created_at).getTime() > lastRead;
                  return (
                    <div key={ev.id} className={cn("flex items-start gap-3 px-4 py-3 hover:bg-zinc-800/30 transition-colors", isUnread && "bg-indigo-600/5")}>
                      <span className={cn("mt-1.5 h-1.5 w-1.5 rounded-full shrink-0", severityDot[ev.severity] ?? "bg-zinc-500")} />
                      <div className="flex-1 min-w-0">
                        <p className={cn("text-xs leading-snug truncate", isUnread ? "text-zinc-200 font-medium" : "text-zinc-300")}>{ev.description}</p>
                        <p className="text-[10px] text-zinc-600 font-mono mt-0.5">{ev.agent_name} · {timeAgo(ev.created_at)}</p>
                      </div>
                      {isUnread && <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-indigo-500 shrink-0" />}
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>
    </header>
  );
}
