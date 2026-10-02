"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getJSON, type CompanyCard } from "@/lib/api";
import { inr, shortName } from "@/lib/format";
import { Monogram, RiskBadge } from "./ui";

export default function CompanySearch({ large = false, placeholder = "Search a company, e.g. Nexora" }: { large?: boolean; placeholder?: string }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<CompanyCard[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!q.trim()) return;
    const t = setTimeout(() => {
      getJSON<CompanyCard[]>(`/companies?q=${encodeURIComponent(q)}&sort=uploads`).then((r) => {
        setResults(r.slice(0, 6));
        setActive(0);
      }).catch(() => setResults([]));
    }, 180);
    return () => clearTimeout(t);
  }, [q]);

  useEffect(() => {
    const close = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const shown = q.trim() ? results : [];
  const go = (c?: CompanyCard) => {
    if (c) router.push(`/companies/${c.id}`);
    else router.push(`/companies?q=${encodeURIComponent(q)}`);
  };

  return (
    <div ref={box} className="relative w-full">
      <form
        onSubmit={(e) => { e.preventDefault(); go(shown[active]); }}
        className={`group flex items-center gap-3 rounded-2xl bg-white ring-1 ring-slate-200 shadow-[0_10px_40px_-12px_rgba(79,70,229,0.35)] transition focus-within:ring-2 focus-within:ring-brand-400 ${large ? "p-2 pl-5" : "p-1.5 pl-4"}`}
      >
        <Search className="h-5 w-5 shrink-0 text-brand-500" />
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, shown.length - 1)); }
            if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
          }}
          placeholder={placeholder}
          aria-label="Search companies"
          className={`min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-slate-400 ${large ? "py-2.5 text-base sm:text-lg" : "py-2 text-sm"}`}
        />
        <button className={`inline-flex shrink-0 items-center gap-1.5 rounded-xl bg-brand-600 font-semibold text-white transition hover:bg-brand-700 ${large ? "px-5 py-3 text-sm" : "px-3.5 py-2 text-sm"}`}>
          Check <ArrowRight className="h-4 w-4" />
        </button>
      </form>
      <AnimatePresence>
        {open && shown.length > 0 && (
          <motion.ul initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
            className="absolute inset-x-0 top-full z-40 mt-2 overflow-hidden rounded-2xl bg-white p-1.5 shadow-2xl ring-1 ring-slate-200">
            {shown.map((c, i) => (
              <li key={c.id}>
                <button onMouseEnter={() => setActive(i)} onClick={() => go(c)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${i === active ? "bg-brand-50" : ""}`}>
                  <Monogram id={c.id} name={c.name} size="sm" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-semibold text-ink">{shortName(c.name)}</span>
                    <span className="block text-xs text-ink-3">
                      {c.summary ? (c.summary.typical_bond_months ? `${c.summary.typical_bond_months}-month bond · ${inr(c.summary.typical_penalty)}` : "No bond reported") : "No verified data yet"}
                      {" · "}{c.verified_uploads} uploads
                    </span>
                  </span>
                  <RiskBadge risk={c.summary?.risk} />
                </button>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
