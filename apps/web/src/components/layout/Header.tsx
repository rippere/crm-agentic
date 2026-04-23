"use client";

import { Search, Bell, Command } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";

interface HeaderProps {
  title: string;
  subtitle?: string;
}

export default function Header({ title, subtitle }: HeaderProps) {
  const [searchFocused, setSearchFocused] = useState(false);

  return (
    <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-xl px-6 py-4">
      {/* Page title */}
      <div className="flex-1 min-w-0">
        <h1 className="text-lg font-semibold text-zinc-100 truncate">{title}</h1>
        {subtitle && (
          <p className="text-xs text-zinc-500 mt-0.5 truncate font-mono">{subtitle}</p>
        )}
      </div>

      {/* Search bar */}
      <div
        className={cn(
          "relative flex items-center gap-2 rounded-xl border bg-zinc-900 px-3 py-2 transition-all duration-200 w-64",
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
      <button
        className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-zinc-800 bg-zinc-900 text-zinc-400 hover:text-zinc-100 hover:border-zinc-700 transition-all duration-200 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-zinc-950"
        aria-label="Notifications (3 unread)"
      >
        <Bell className="h-4 w-4" aria-hidden="true" />
        <span className="absolute -top-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-indigo-600 text-[9px] font-bold text-white">
          3
        </span>
      </button>
    </header>
  );
}
