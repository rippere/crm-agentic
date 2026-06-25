"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, Zap } from "lucide-react";
import Sidebar from "@/components/layout/Sidebar";
import CommandPalette from "@/components/ui/CommandPalette";
import type { WorkspaceMode } from "@/lib/types";

const transitionProps = {
  type: "tween" as const,
  ease: "easeOut" as const,
  duration: 0.2,
};

interface ClientShellProps {
  children: React.ReactNode;
  mode: WorkspaceMode;
  userEmail?: string;
  userName?: string;
  /** Owner-private: gates the Life nav item. Resolved server-side from the allowlist. */
  lifeEnabled?: boolean;
}

export default function ClientShell({ children, mode, userEmail = "", userName = "User", lifeEnabled = false }: ClientShellProps) {
  const [cmdOpen, setCmdOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);
  const [isMobile, setIsMobile] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  const openPalette = useCallback(() => setCmdOpen(true), []);
  const closePalette = useCallback(() => setCmdOpen(false), []);
  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);

  // Track viewport: off-canvas drawer on mobile, hover-rail on desktop (md = 768px)
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  // Lock body scroll while the mobile drawer is open
  useEffect(() => {
    if (mobileNavOpen) {
      document.body.style.overflow = "hidden";
      return () => { document.body.style.overflow = ""; };
    }
  }, [mobileNavOpen]);

  // Close the drawer if we grow past the mobile breakpoint
  useEffect(() => {
    if (!isMobile) setMobileNavOpen(false);
  }, [isMobile]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
      if (e.key === "Escape") setMobileNavOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      {/* Mobile top bar — hamburger + brand (hidden on md+) */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-30 flex h-14 items-center gap-3 border-b border-zinc-800/50 bg-[#08080C]/95 backdrop-blur-xl px-3">
        <button
          onClick={() => setMobileNavOpen(true)}
          className="flex h-11 w-11 items-center justify-center rounded-lg text-zinc-300 hover:bg-zinc-800/60 active:bg-zinc-800 transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-500"
          aria-label="Open navigation menu"
          aria-expanded={mobileNavOpen}
        >
          <Menu className="h-5 w-5" aria-hidden="true" />
        </button>
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-indigo-600">
            <Zap className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
          <span className="text-sm font-semibold text-zinc-100 tracking-tight">NovaCRM</span>
        </div>
      </div>

      <Sidebar
        mode={mode}
        userEmail={userEmail}
        userName={userName}
        lifeEnabled={lifeEnabled}
        onSearchClick={openPalette}
        isCollapsed={sidebarCollapsed}
        onExpand={() => setSidebarCollapsed(false)}
        onCollapse={() => setSidebarCollapsed(true)}
        isMobile={isMobile}
        mobileOpen={mobileNavOpen}
        onMobileClose={closeMobileNav}
      />

      {/* Backdrop for the mobile drawer */}
      <AnimatePresence>
        {isMobile && mobileNavOpen && (
          <motion.div
            className="fixed inset-0 z-40 bg-black/60 md:hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={closeMobileNav}
            aria-hidden="true"
          />
        )}
      </AnimatePresence>

      {/* Main content — margin tracks the sidebar width on desktop; full-width on mobile */}
      <motion.main
        className="flex-1 overflow-y-auto min-h-screen pt-14 md:pt-0"
        animate={{ marginLeft: isMobile ? 0 : sidebarCollapsed ? "3.5rem" : "15rem" }}
        transition={transitionProps}
      >
        {children}
      </motion.main>

      <AnimatePresence>
        {cmdOpen && (
          <CommandPalette
            key="command-palette"
            onClose={closePalette}
            onSubmit={(value) => {
              console.log("[NovaCRM AI]", value);
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}
