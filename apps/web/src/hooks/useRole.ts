"use client";

import { useState, useEffect } from "react";
import { createBrowserClient } from "@/lib/supabase";

export type UserRole = "admin" | "member" | null;

interface UseRoleResult {
  role: UserRole;
  isAdmin: boolean;
  loading: boolean;
}

export function useRole(): UseRoleResult {
  const [role, setRole] = useState<UserRole>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (process.env.NEXT_PUBLIC_DEMO_MODE === "true") {
      setRole("admin");
      setLoading(false);
      return;
    }

    const supabase = createBrowserClient();
    supabase.auth.getSession().then(async ({ data: { session } }) => {
      if (!session) { setLoading(false); return; }
      try {
        const res = await fetch(
          `${process.env.NEXT_PUBLIC_FASTAPI_URL || "http://localhost:8000"}/me`,
          { headers: { Authorization: `Bearer ${session.access_token}` } }
        );
        if (res.ok) {
          const data = await res.json();
          setRole(data.role as UserRole);
        }
      } catch { /* ignore */ } finally {
        setLoading(false);
      }
    });
  }, []);

  return { role, isAdmin: role === "admin", loading };
}
