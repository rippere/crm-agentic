"use client";

import { cn } from "@/lib/utils";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
  glow?: boolean;
}

export default function Card({ children, className, hover = false, glow = false, ...props }: CardProps) {
  return (
    <div
      {...props}
      className={cn(
        "rounded-xl border border-zinc-800 bg-zinc-900 p-4",
        hover && "cursor-pointer transition-all duration-200 hover:border-zinc-700 hover:bg-zinc-800/80",
        glow && "hover:shadow-glow-sm hover:border-indigo-500/30",
        className
      )}
    >
      {children}
    </div>
  );
}
