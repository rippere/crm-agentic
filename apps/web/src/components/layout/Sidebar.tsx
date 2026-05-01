"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { createBrowserClient } from "@/lib/supabase";
import type { AgentRow } from "@/lib/supabase";
import {
  LayoutDashboard, Users, KanbanSquare, Bot, Settings,
  Zap, Inbox, CheckSquare, FolderOpen, Plug, Search,
  PhoneCall, ChevronsUpDown, LogOut, BarChart2,
} from "lucide-react";
import type { WorkspaceMode } from "@/lib/types";

/* ─── Framer variants ─── */

const sidebarVariants = {
  open:   { width: "15rem"  },
  closed: { width: "3.5rem" },
};

const transitionProps = {
  type: "tween" as const,
  ease: "easeOut" as const,
  duration: 0.2,
};

const labelVariants = {
  open:   { opacity: 1, x: 0,  display: "block", transition: { delay: 0.05 } },
  closed: { opacity: 0, x: -8, transitionEnd: { display: "none" } },
};

/* ─── Nav structure ─── */

interface NavItem {
  href: string;
  label: string;
  icon: React.ElementType;
  hideModes?: WorkspaceMode[];
  badge?: string;
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
      { href: "/contacts",  label: "Contacts",  icon: Users            },
      { href: "/pipeline",  label: "Pipeline",  icon: KanbanSquare,  hideModes: ["pm"] },
      { href: "/reports",   label: "Reports",   icon: BarChart2,     hideModes: ["pm"] },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { href: "/agents",   label: "Agents",   icon: Bot,         badge: "LIVE" },
      { href: "/inbox",    label: "Inbox",    icon: Inbox                       },
      { href: "/calls",    label: "Calls",    icon: PhoneCall                   },
      { href: "/tasks",    label: "Tasks",    icon: CheckSquare, hideModes: ["sales"] },
      { href: "/projects", label: "Projects", icon: FolderOpen,  hideModes: ["sales"] },
    ],
  },
  {
    id: "system",
    label: "System",
    items: [
      { href: "/connectors", label: "Connectors", icon: Plug     },
      { href: "/settings",   label: "Settings",   icon: Settings },
    ],
  },
];

function getInitials(name: string, email: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  if (parts[0]?.length >= 2) return parts[0].slice(0, 2).toUpperCase();
  return email.slice(0, 2).toUpperCase();
}

interface SidebarProps {
  mode?: WorkspaceMode;
  userEmail?: string;
  userName?: string;
  onSearchClick?: () => void;
  isCollapsed: boolean;
  onExpand: () => void;
  onCollapse: () => void;
}

export default function Sidebar({
  mode = "sales",
  userEmail = "",
  userName = "User",
  onSearchClick,
  isCollapsed,
  onExpand,
  onCollapse,
}: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Real agent status for Nexus
  const [nexusAgents, setNexusAgents] = useState<Pick<AgentRow, "name" | "status">[]>([]);

  useEffect(() => {
    const supabase = createBrowserClient();
    supabase
      .from("agents")
      .select("name, status")
      .limit(4)
      .then(({ data }) => {
        if (data && data.length > 0) setNexusAgents(data);
      });
  }, []);

  // Close menu on outside click
  useEffect(() => {
    if (!userMenuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setUserMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [userMenuOpen]);

  const handleLogout = async () => {
    const supabase = createBrowserClient();
    await supabase.auth.signOut();
    router.push("/login");
  };

  const initials = getInitials(userName, userEmail);
  const activeCount = nexusAgents.filter((a) => a.status === "active").length;

  return (
    <motion.aside
      className="fixed left-0 top-0 h-full z-30 flex flex-col border-r border-zinc-800/50 overflow-hidden"
      style={{ backgroundColor: "#08080C" }}
      initial="closed"
      animate={isCollapsed ? "closed" : "open"}
      variants={sidebarVariants}
      transition={transitionProps}
      onMouseEnter={onExpand}
      onMouseLeave={onCollapse}
    >
      {/* Logo */}
      <div className="flex h-[54px] shrink-0 items-center gap-3 px-3 border-b border-zinc-800/50">
        <div
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600"
          style={{ boxShadow: "0 0 14px rgba(99,102,241,0.45)" }}
        >
          <Zap className="h-4 w-4 text-white" aria-hidden="true" />
        </div>
        <motion.div variants={labelVariants} className="min-w-0 flex-1 overflow-hidden whitespace-nowrap">
          <p className="text-sm font-semibold text-zinc-100 leading-none tracking-tight">NovaCRM</p>
          <p className="text-[10px] text-zinc-500 mt-0.5 font-mono">Agentic Intelligence</p>
        </motion.div>
        <motion.div
          variants={labelVariants}
          className="flex items-center gap-1 flex-shrink-0"
          title="All systems operational"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-[#00C896] agent-pulse" />
          <span className="text-[10px] font-mono font-semibold text-[#00C896] tracking-widest">LIVE</span>
        </motion.div>
      </div>

      {/* Search / ⌘K */}
      <div className="px-2 pt-3 pb-1">
        <button
          onClick={onSearchClick}
          className="group w-full flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/60 px-2.5 py-2 text-sm text-zinc-600 hover:text-zinc-400 hover:border-zinc-700 transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500"
          aria-label="Open command palette (⌘K)"
        >
          <Search className="h-4 w-4 shrink-0 text-zinc-700 group-hover:text-zinc-500 transition-colors" aria-hidden="true" />
          <motion.span variants={labelVariants} className="flex-1 text-left text-xs whitespace-nowrap">
            Search…
          </motion.span>
          <motion.kbd
            variants={labelVariants}
            className="flex items-center rounded border border-zinc-800 bg-zinc-900/60 px-1.5 py-0.5 text-[9px] font-mono text-zinc-700"
          >
            ⌘K
          </motion.kbd>
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-2 py-2 overflow-y-auto overflow-x-hidden" aria-label="Main navigation">
        <div className="space-y-4">
          {navGroups.map(({ id, label, items }) => {
            const visible = items.filter((item) => !item.hideModes?.includes(mode));
            if (visible.length === 0) return null;

            return (
              <div key={id}>
                <motion.p
                  variants={labelVariants}
                  className="px-2.5 mb-1 text-[10px] font-semibold uppercase tracking-[0.14em] font-mono text-zinc-500 whitespace-nowrap overflow-hidden"
                >
                  {label}
                </motion.p>
                <div className="space-y-0.5">
                  {visible.map(({ href, label: itemLabel, icon: Icon, badge }) => {
                    const active = pathname === href || pathname.startsWith(href + "/");
                    return (
                      <Link
                        key={href}
                        href={href}
                        className={cn(
                          "group relative flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm font-medium transition-all duration-150 whitespace-nowrap",
                          active
                            ? "bg-indigo-500/10 text-zinc-100"
                            : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/40"
                        )}
                        aria-current={active ? "page" : undefined}
                        title={itemLabel}
                      >
                        {active && (
                          <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-0.5 rounded-full bg-indigo-500" />
                        )}
                        <Icon
                          className={cn(
                            "h-4 w-4 shrink-0 transition-colors duration-150",
                            active ? "text-indigo-400" : "text-zinc-600 group-hover:text-zinc-400"
                          )}
                          aria-hidden="true"
                        />
                        <motion.span variants={labelVariants} className="flex-1 overflow-hidden">
                          {itemLabel}
                        </motion.span>
                        {badge && (
                          <motion.span
                            variants={labelVariants}
                            className="text-[8px] font-mono font-semibold text-[#00C896] border border-[#00C896]/30 rounded px-1 py-0.5 leading-none bg-[#00C896]/5"
                          >
                            {badge}
                          </motion.span>
                        )}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </nav>

      {/* Nexus — live agent status */}
      <div className="px-3 py-3 border-t border-zinc-800/50 shrink-0">
        <motion.div variants={labelVariants}>
          <div className="flex items-center justify-between mb-2">
            <p className="text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Nexus
            </p>
            <span className="text-[10px] font-mono text-zinc-600">
              {nexusAgents.length > 0 ? `${activeCount} active` : "—"}
            </span>
          </div>
          <div className="space-y-1.5">
            {nexusAgents.map((agent) => (
              <div key={agent.name} className="flex items-center gap-2.5">
                <span
                  className={cn(
                    "h-1.5 w-1.5 rounded-full shrink-0",
                    agent.status === "active"
                      ? "bg-[#00C896] agent-pulse"
                      : agent.status === "processing"
                      ? "bg-indigo-400"
                      : "bg-zinc-600"
                  )}
                />
                <span className="text-[11px] text-zinc-500 flex-1 truncate font-medium">{agent.name}</span>
                <span className={cn(
                  "text-[10px] font-mono shrink-0",
                  agent.status === "active" ? "text-[#00C896]/60" : "text-zinc-600"
                )}>
                  {agent.status}
                </span>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div
          initial={false}
          animate={isCollapsed ? { opacity: 1 } : { opacity: 0 }}
          transition={{ duration: 0.1 }}
          className="space-y-1.5 absolute pointer-events-none"
          aria-hidden="true"
        >
          {nexusAgents.map((agent) => (
            <span
              key={agent.name}
              className={cn(
                "h-1.5 w-1.5 rounded-full block",
                agent.status === "active" ? "bg-[#00C896] agent-pulse" : "bg-zinc-700"
              )}
            />
          ))}
        </motion.div>
      </div>

      {/* User menu */}
      <div ref={menuRef} className="px-2 py-2 border-t border-zinc-800/50 shrink-0 relative">
        <AnimatePresence>
          {userMenuOpen && (
            <motion.div
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 4 }}
              transition={{ duration: 0.15 }}
              className="absolute bottom-full left-2 right-2 mb-1 rounded-xl border border-zinc-800 bg-zinc-900 shadow-xl overflow-hidden z-50"
            >
              <div className="px-3 py-2.5 border-b border-zinc-800">
                <p className="text-xs font-semibold text-zinc-200 truncate">{userName}</p>
                <p className="text-[10px] text-zinc-500 font-mono truncate mt-0.5">{userEmail}</p>
              </div>
              <button
                onClick={handleLogout}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 text-sm text-zinc-400 hover:text-red-400 hover:bg-red-500/5 transition-colors cursor-pointer"
              >
                <LogOut className="h-3.5 w-3.5" />
                <span className="text-xs">Sign out</span>
              </button>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          onClick={() => setUserMenuOpen((v) => !v)}
          className="w-full flex items-center gap-3 px-2.5 py-2 rounded-lg hover:bg-zinc-800/40 transition-all cursor-pointer whitespace-nowrap group"
          aria-label="User menu"
          aria-expanded={userMenuOpen}
        >
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-500/15 border border-indigo-500/25 text-[10px] font-semibold text-indigo-300 font-mono">
            {initials}
          </div>
          <motion.div variants={labelVariants} className="flex-1 min-w-0 overflow-hidden text-left">
            <p className="text-xs font-semibold text-zinc-300 truncate leading-none">{userName}</p>
            <p className="text-[10px] text-zinc-600 font-mono mt-0.5 truncate">{userEmail}</p>
          </motion.div>
          <motion.div variants={labelVariants} className="shrink-0">
            <ChevronsUpDown className="h-3.5 w-3.5 text-zinc-700 group-hover:text-zinc-500 transition-colors" />
          </motion.div>
        </button>
      </div>
    </motion.aside>
  );
}
