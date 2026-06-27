"use client";

// ─── Trust strip ─────────────────────────────────────────────────────────────
// Monochrome wordmark row — the visual rhythm of social proof without fake
// brand logos. Companies match the names used in the Testimonials section.
const companies = ["Lumen Logistics", "Solvio", "Northwind", "Caldera", "Brightpath", "ScaleUp"];

export function TrustStrip() {
  return (
    <section className="px-6 pb-8" aria-label="Customers">
      <div className="mx-auto max-w-5xl">
        <p className="text-center text-xs font-mono uppercase tracking-widest text-zinc-600">
          Powering pipelines at fast-growing revenue teams
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-10 gap-y-4">
          {companies.map((name) => (
            <span
              key={name}
              className="text-base font-semibold tracking-tight text-zinc-600 transition-colors duration-200 hover:text-zinc-400 sm:text-lg"
            >
              {name}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
