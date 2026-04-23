"use client";

import { cn } from "@/lib/utils";

interface AvatarProps {
  initials: string;
  size?: "xs" | "sm" | "md" | "lg";
  color?: "indigo" | "emerald" | "amber" | "rose";
  className?: string;
}

const sizeClasses = {
  xs: "h-6 w-6 text-[10px]",
  sm: "h-8 w-8 text-xs",
  md: "h-10 w-10 text-sm",
  lg: "h-12 w-12 text-base",
};

const colorClasses = {
  indigo: "bg-indigo-500/20 text-indigo-300 border border-indigo-500/30",
  emerald: "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30",
  amber: "bg-amber-500/20 text-amber-300 border border-amber-500/30",
  rose: "bg-rose-500/20 text-rose-300 border border-rose-500/30",
};

const autoColor = (initials: string): keyof typeof colorClasses => {
  const colors: (keyof typeof colorClasses)[] = ["indigo", "emerald", "amber", "rose"];
  const idx = (initials.charCodeAt(0) + (initials.charCodeAt(1) || 0)) % colors.length;
  return colors[idx];
};

export default function Avatar({ initials, size = "md", color, className }: AvatarProps) {
  const resolvedColor = color ?? autoColor(initials);
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-full font-semibold font-mono flex-shrink-0",
        sizeClasses[size],
        colorClasses[resolvedColor],
        className
      )}
    >
      {initials}
    </div>
  );
}
