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
  Inbox,
  CheckSquare,
  FolderOpen,
  Plug,
  Search,
  PhoneCall,
} from "lucide-react";
import type { WorkspaceMode } from "@/lib/types";

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  modes?: WorkspaceMode[];
  hideModes?: WorkspaceMode[];
}

interface NavGroup {
  id: string;
  label: string;
  items: NavItem[];
}

const navGroups: NavGroup[] = [
  {
    id: "workspace",
    label: "Workspace",
    items: [
      { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
      { href: "/contacts", label: "Contacts", icon: Users },
      { href: "/pipeline", label: "Pipeline", icon: KanbanSquare, hideModes: ["pm"] },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { href: "/agents", label: "Agents", icon: Bot },
      { href: "/inbox", label: "Inbox", icon: Inbox },
      { href: "/calls", label: "Calls", icon: PhoneCall },
      { href: "/tasks", label: "Tasks", icon: CheckSquare, hideModes: ["sales"] },
      { href: "/projects", label: "Projects", icon: FolderOpen, hideModes: ["sales"] },
    ],
  },
  {
    id: "system",
    label: "System",
    items: [
      { href: "/connectors", label: "Connectors", icon: Plug },
    ],
  },
];

const agentNexus = [
  { name: "Semantic Sorter",   status: "active"     as const, metric: "12/min" },
  { name: "Lead Scorer",       status: "active"     as const, metric: "8/min"  },
  { name: "Email Composer",    status: "processing" as const, metric: "ready"  },
  { name: "Sentiment Analyzer", status: "active"    as const, metric: "15/min" },
];

interface SidebarProps {
  mode?: WorkspaceMode;
}

export default function Sidebar({ mode = "sales" }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className="fixed left-0 top-0 h-full w-60 flex flex-col z-30 border-r border-zinc-800/50"
      style={{ backgroundColor: "#08080C" }}
    >
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-zinc-800/50">
        <div
          className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 flex-shrink-0"
          style={{ boxShadow: "0 0 14px rgba(99,102,241,0.45)" }}
        >
          <Zap className="h-4 w-4 text-white" aria-hidden="true" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-zinc-100 leading-none tracking-tight">NovaCRM</p>
          <p className="text-[10px] text-zinc-500 mt-0.5 font-mono">Agentic Intelligence</p>
        </div>
        <div
          className="flex items-center gap-1 flex-shrink-0"
          aria-label="System live"
          title="All systems operational"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-[#00C896] agent-pulse" />
          <span className="text-[9px] font-mono font-semibold text-[#00C896] tracking-widest">LIVE</span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-4 overflow-y-auto" aria-label="Main navigation">
        <div className="space-y-5">
          {navGroups.map(({ id, label, items }) => {
            const visible = items.filter((item) => {
              if (item.hideModes?.includes(mode)) return false;
              if (item.modes && !item.modes.includes(mode)) return false;
              return true;
            });
            if (visible.length === 0) return null;

            return (
              <div key={id}>
                <p className="px-3 mb-1 text-[9px] font-semibold uppercase tracking-[0.14em] font-mono text-zinc-600">
                  {label}
                </p>
                <div className="space-y-0.5">
                  {visible.map(({ href, label: itemLabel, icon: Icon }) => {
                    const active = pathname === href || pathname.startsWith(href + "/");
                    return (
                      <Link
                        key={href}
                        href={href}
                        className={cn(
                          "group relative flex items-center gap-3 rounded-r-lg px-3 py-2 text-sm font-medium transition-all duration-150",
                          "border-l-2",
                          active
                            ? "border-l-indigo-500 bg-indigo-500/8 text-zinc-100"
                            : "border-l-transparent text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/25"
                        )}
                        aria-current={active ? "page" : undefined}
                      >
                        <Icon
                          className={cn(
                            "h-4 w-4 flex-shrink-0 transition-colors duration-150",
                            active ? "text-indigo-400" : "text-zinc-600 group-hover:text-zinc-400"
                          )}
                          aria-hidden="true"
                        />
                        {itemLabel}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}

          {/* Command palette shortcut */}
          <button
            className="group w-full flex items-center gap-3 rounded-r-lg border-l-2 border-l-transparent px-3 py-2 text-sm font-medium text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/20 transition-all duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500"
            aria-label="Open command palette (⌘K)"
          >
            <Search className="h-4 w-4 flex-shrink-0 text-zinc-700 group-hover:text-zinc-500 transition-colors" aria-hidden="true" />
            <span>Search</span>
            <kbd className="ml-auto flex items-center gap-0.5 rounded border border-zinc-800 bg-zinc-900/60 px-1.5 py-0.5 text-[9px] font-mono text-zinc-700">
              ⌘K
            </kbd>
          </button>
        </div>
      </nav>

      {/* Nexus — live agent status with throughput */}
      <div className="px-4 py-3 border-t border-zinc-800/50">
        <div className="flex items-center justify-between mb-2.5">
          <p className="text-[9px] font-mono font-semibold uppercase tracking-[0.14em] text-zinc-600">
            Nexus
          </p>
          <span className="text-[9px] font-mono text-zinc-700">
            {agentNexus.filter(a => a.status === "active").length} active
          </span>
        </div>
        <div className="space-y-1.5">
          {agentNexus.map((agent) => (
            <div key={agent.name} className="flex items-center gap-2.5">
              <span
                className={cn(
                  "h-1.5 w-1.5 rounded-full flex-shrink-0",
                  agent.status === "active"
                    ? "bg-[#00C896] agent-pulse"
                    : agent.status === "processing"
                    ? "bg-indigo-400"
                    : "bg-zinc-600"
                )}
              />
              <span className="text-[11px] text-zinc-500 flex-1 truncate min-w-0 font-medium">
                {agent.name}
              </span>
              <span
                className={cn(
                  "text-[10px] font-mono flex-shrink-0",
                  agent.status === "active" ? "text-[#00C896]/60" : "text-zinc-600"
                )}
              >
                {agent.metric}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Settings + User */}
      <div className="px-2 py-3 border-t border-zinc-800/50 space-y-0.5">
        <Link
          href="/settings"
          className="group flex items-center gap-3 rounded-r-lg border-l-2 border-l-transparent px-3 py-2 text-sm font-medium text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/25 transition-all duration-150 cursor-pointer"
        >
          <Settings
            className="h-4 w-4 flex-shrink-0 text-zinc-600 group-hover:text-zinc-400 transition-colors"
            aria-hidden="true"
          />
          Settings
        </Link>
        <div className="flex items-center gap-3 px-3 py-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-indigo-500/15 border border-indigo-500/25 text-[10px] font-semibold text-indigo-300 font-mono flex-shrink-0">
            BR
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-semibold text-zinc-300 truncate leading-none">Ben Wilson</p>
            <p className="text-[10px] text-zinc-600 truncate font-mono mt-0.5">Admin · Pro</p>
          </div>
        </div>
      </div>
    </aside>
  );
}
