"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import Sidebar from "@/components/layout/Sidebar";
import CommandPalette from "@/components/ui/CommandPalette";
import type { WorkspaceMode } from "@/lib/types";

interface ClientShellProps {
  children: React.ReactNode;
  mode: WorkspaceMode;
}

export default function ClientShell({ children, mode }: ClientShellProps) {
  const [cmdOpen, setCmdOpen] = useState(false);

  const openPalette = useCallback(() => setCmdOpen(true),  []);
  const closePalette = useCallback(() => setCmdOpen(false), []);

  // Global ⌘K / Ctrl+K shortcut
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
      <Sidebar mode={mode} onSearchClick={openPalette} />

      {/* Main content — slides from 56px (collapsed) to 240px (expanded) matching sidebar */}
      <motion.main
        className="flex-1 overflow-y-auto min-h-screen"
        initial={{ marginLeft: "3.5rem" }}
        style={{ marginLeft: "3.5rem" }}
      >
        {children}
      </motion.main>

      {cmdOpen && (
        <CommandPalette
          onClose={closePalette}
          onSubmit={(value) => {
            console.log("[NovaCRM AI]", value);
            // TODO: wire to actual AI agent endpoint
          }}
        />
      )}
    </>
  );
}
