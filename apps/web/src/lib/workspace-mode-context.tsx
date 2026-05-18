"use client";

import { createContext, useContext, useState, useEffect, type ReactNode } from "react";
import type { WorkspaceMode } from "./types";

const STORAGE_KEY = "novacrm_demo_mode";
const IS_DEMO = process.env.NEXT_PUBLIC_DEMO_MODE === "true";

interface WorkspaceModeContextValue {
  mode: WorkspaceMode;
  setMode: (m: WorkspaceMode) => void;
}

const WorkspaceModeContext = createContext<WorkspaceModeContextValue>({
  mode: "both",
  setMode: () => {},
});

export function WorkspaceModeProvider({
  children,
  initialMode,
}: {
  children: ReactNode;
  initialMode: WorkspaceMode;
}) {
  const [mode, setModeState] = useState<WorkspaceMode>(initialMode);

  // In demo mode, hydrate from localStorage after mount
  useEffect(() => {
    if (!IS_DEMO) return;
    const stored = localStorage.getItem(STORAGE_KEY) as WorkspaceMode | null;
    if (stored === "sales" || stored === "pm" || stored === "both") {
      setModeState(stored);
    }
  }, []);

  const setMode = (m: WorkspaceMode) => {
    setModeState(m);
    if (IS_DEMO) localStorage.setItem(STORAGE_KEY, m);
  };

  return (
    <WorkspaceModeContext.Provider value={{ mode, setMode }}>
      {children}
    </WorkspaceModeContext.Provider>
  );
}

export function useWorkspaceMode() {
  return useContext(WorkspaceModeContext);
}
