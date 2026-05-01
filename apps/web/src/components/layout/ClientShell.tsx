"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
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
}

export default function ClientShell({ children, mode, userEmail = "", userName = "User" }: ClientShellProps) {
  const [cmdOpen, setCmdOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(true);

  const openPalette = useCallback(() => setCmdOpen(true), []);
  const closePalette = useCallback(() => setCmdOpen(false), []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setCmdOpen((v) => !v);
      }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  return (
    <>
      <Sidebar
        mode={mode}
        userEmail={userEmail}
        userName={userName}
        onSearchClick={openPalette}
        isCollapsed={sidebarCollapsed}
        onExpand={() => setSidebarCollapsed(false)}
        onCollapse={() => setSidebarCollapsed(true)}
      />

      {/* Main content — margin tracks the sidebar width so content is never obscured */}
      <motion.main
        className="flex-1 overflow-y-auto min-h-screen"
        animate={{ marginLeft: sidebarCollapsed ? "3.5rem" : "15rem" }}
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
