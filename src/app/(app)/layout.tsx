import Sidebar from "@/components/layout/Sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-zinc-950">
      <Sidebar />
      <main className="ml-60 flex-1 overflow-y-auto min-h-screen">
        {children}
      </main>
    </div>
  );
}
