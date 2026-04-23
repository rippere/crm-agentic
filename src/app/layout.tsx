import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NovaCRM — Agentic Intelligence",
  description:
    "AI-native CRM powered by semantic sorting, ML lead scoring, and autonomous agents.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-zinc-950 text-zinc-100">{children}</body>
    </html>
  );
}
