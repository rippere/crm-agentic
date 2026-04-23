"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import {
  LayoutDashboard,
  Users,
  KanbanSquare,
  Bot,
  Settings,
  Zap,
  ChevronRight,
  Inbox,
  CheckSquare,
  FolderOpen,
  Plug,
} from "lucide-react";
import type { WorkspaceMode } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  /** If set, only show when mode is in this list */
  modes?: WorkspaceMode[];
  /** If set, hide when mode is in this list */
  hideModes?: WorkspaceMode[];
}

const navItems: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/contacts", label: "Contacts", icon: Users },
  { href: "/pipeline", label: "Pipeline", icon: KanbanSquare, hideModes: ["pm"] },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/inbox", label: "Inbox", icon: Inbox },
  { href: "/tasks", label: "Tasks", icon: CheckSquare, hideModes: ["sales"] },
  { href: "/projects", label: "Projects", icon: FolderOpen, hideModes: ["sales"] },
  { href: "/connectors", label: "Connectors", icon: Plug },
];

const agentStatuses = [
  { name: "Semantic Sorter", status: "active" as const },
  { name: "Lead Scorer", status: "active" as const },
  { name: "Email Composer", status: "processing" as const },
  { name: "Sentiment Analyzer", status: "active" as const },
];

const statusDot = {
  active: "bg-emerald-400 agent-pulse",
  processing: "bg-indigo-400",
  idle: "bg-zinc-500",
  error: "bg-rose-400",
};

interface SidebarProps {
  mode?: WorkspaceMode;
}

export default function Sidebar({ mode = "sales" }: SidebarProps) {
  const pathname = usePathname();

  const visibleItems = navItems.filter((item) => {
    if (item.hideModes && item.hideModes.includes(mode)) return false;
    if (item.modes && !item.modes.includes(mode)) return false;
    return true;
  });

  return (
    <aside className="fixed left-0 top-0 h-full w-60 border-r border-zinc-800 bg-zinc-950 flex flex-col z-30">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-zinc-800">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 shadow-glow-sm">
          <Zap className="h-4 w-4 text-white" aria-hidden="true" />
        </div>
        <div>
          <p className="text-sm font-semibold text-zinc-100 leading-none">NovaCRM</p>
          <p className="text-[10px] text-zinc-500 mt-0.5 font-mono">Agentic Intelligence</p>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto" aria-label="Main navigation">
        {visibleItems.map(({ href, label, icon: Icon }) => {
          const active = pathname === href || pathname.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all duration-200 group cursor-pointer",
                active
                  ? "bg-indigo-600/15 text-indigo-300 border border-indigo-500/20"
                  : "text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800/80"
              )}
              aria-current={active ? "page" : undefined}
            >
              <Icon
                className={cn(
                  "h-4 w-4 flex-shrink-0",
                  active ? "text-indigo-400" : "text-zinc-500 group-hover:text-zinc-300"
                )}
                aria-hidden="true"
              />
              <span className="font-medium">{label}</span>
              {active && (
                <ChevronRight className="ml-auto h-3.5 w-3.5 text-indigo-500" aria-hidden="true" />
              )}
            </Link>
          );
        })}
      </nav>

      {/* Live Agent Status */}
      <div className="px-4 py-4 border-t border-zinc-800">
        <p className="text-[10px] font-mono text-zinc-500 uppercase tracking-widest mb-3">
          Live Agents
        </p>
        <div className="space-y-2">
          {agentStatuses.map((agent) => (
            <div key={agent.name} className="flex items-center gap-2.5">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full flex-shrink-0",
                  statusDot[agent.status]
                )}
              />
              <span className="text-xs text-zinc-400 truncate">{agent.name}</span>
            </div>
          ))}
        </div>
      </div>

      {/* User / Settings */}
      <div className="px-3 py-3 border-t border-zinc-800">
        <Link
          href="/settings"
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-all duration-200 cursor-pointer group"
        >
          <Settings className="h-4 w-4 flex-shrink-0 text-zinc-500 group-hover:text-zinc-300" aria-hidden="true" />
          <span className="font-medium">Settings</span>
        </Link>
        <div className="flex items-center gap-3 px-3 py-2.5 mt-1">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500/20 border border-indigo-500/30 text-[11px] font-semibold text-indigo-300 font-mono flex-shrink-0">
            BW
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-zinc-200 truncate">Ben Wilson</p>
            <p className="text-[10px] text-zinc-500 truncate">Admin · Pro Plan</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
