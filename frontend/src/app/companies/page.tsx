"use client";

import { AnimatePresence } from "framer-motion";
import { Building2, Search, SlidersHorizontal } from "lucide-react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import CompanyCardView from "@/components/CompanyCardView";
import { ErrorState, Reveal, Skeleton, useApi } from "@/components/ui";
import { getJSON, type CompanyCard } from "@/lib/api";

const SORTS = [
  ["risk", "Highest risk"],
  ["penalty", "Highest penalty"],
  ["uploads", "Most uploads"],
  ["drive", "Next drive"],
  ["name", "A to Z"],
] as const;

export default function CompaniesPage() {
  return (
    <Suspense>
      <Companies />
    </Suspense>
  );
}

function Companies() {
  const params = useSearchParams();
  const router = useRouter();
  const [q, setQ] = useState(params.get("q") ?? "");
  const [debounced, setDebounced] = useState(q);
  const [bond, setBond] = useState<"any" | "yes" | "no">("any");
  const [sort, setSort] = useState<string>("risk");

  useEffect(() => {
    const t = setTimeout(() => setDebounced(q), 220);
    return () => clearTimeout(t);
  }, [q]);
  useEffect(() => {
    router.replace(debounced ? `/companies?q=${encodeURIComponent(debounced)}` : "/companies", { scroll: false });
  }, [debounced, router]);

  const { data, error, loading, reload } = useApi(
    () => getJSON<CompanyCard[]>(`/companies?q=${encodeURIComponent(debounced)}&bond=${bond}&sort=${sort}`),
    [debounced, bond, sort],
  );
  const withData = useMemo(() => (data ?? []).filter((c) => c.verified_uploads > 0), [data]);
  const noData = useMemo(() => (data ?? []).filter((c) => c.verified_uploads === 0), [data]);

  return (
    <>
      <section className="relative -mt-16 overflow-hidden pb-24 pt-32">
        <Image src="/images/campus.jpg" alt="" fill priority sizes="100vw" className="object-cover" />
        <div className="absolute inset-0 bg-linear-to-b from-ink/85 via-brand-900/80 to-ink/90" />
        <div className="container-x relative">
          <Reveal>
            <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-brand-100 ring-1 ring-white/20"><Building2 className="h-3.5 w-3.5" /> Company directory</p>
            <h1 className="mt-4 max-w-2xl font-display text-4xl font-extrabold text-white sm:text-5xl">Every bond, backed by evidence.</h1>
            <p className="mt-4 max-w-xl text-lg text-slate-300">Terms aggregated from verified, anonymised offer letters. Conflicting reports are shown, never hidden.</p>
          </Reveal>
        </div>
      </section>

      <section className="container-x relative -mt-12">
        <div className="card flex flex-col gap-3 p-3 sm:p-4 lg:flex-row lg:items-center">
          <label className="flex flex-1 items-center gap-3 rounded-xl bg-canvas px-4 ring-1 ring-line focus-within:ring-2 focus-within:ring-brand-300">
            <Search className="h-5 w-5 text-ink-3" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search companies or name variants…" className="h-12 flex-1 bg-transparent outline-none placeholder:text-slate-400" aria-label="Search companies" />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex rounded-xl bg-canvas p-1 ring-1 ring-line">
              {(["any", "yes", "no"] as const).map((b) => (
                <button key={b} onClick={() => setBond(b)} className={`rounded-lg px-3.5 py-2 text-sm font-medium transition ${bond === b ? "bg-white text-ink shadow-sm" : "text-ink-3 hover:text-ink"}`}>
                  {b === "any" ? "All" : b === "yes" ? "With bond" : "No bond"}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2 rounded-xl bg-canvas px-3 ring-1 ring-line">
              <SlidersHorizontal className="h-4 w-4 text-ink-3" />
              <select value={sort} onChange={(e) => setSort(e.target.value)} className="h-11 bg-transparent pr-1 text-sm font-medium text-ink outline-none" aria-label="Sort">
                {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </select>
            </label>
          </div>
        </div>

        <div className="mt-8 flex items-center justify-between text-sm text-ink-3">
          <p>{loading ? "Loading…" : `${withData.length} compan${withData.length === 1 ? "y" : "ies"} with verified data`}</p>
          <p className="hidden sm:block">Risk score explained on each company page</p>
        </div>

        {error && <div className="mt-6"><ErrorState message={error} onRetry={reload} /></div>}
        <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {loading && !data && Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-64" />)}
          <AnimatePresence mode="popLayout">
            {withData.map((c, i) => <CompanyCardView key={c.id} c={c} index={i} />)}
          </AnimatePresence>
        </div>
        {!loading && data && withData.length === 0 && (
          <div className="card mt-6 p-12 text-center">
            <p className="font-display text-lg font-bold text-ink">No companies match.</p>
            <p className="mt-1 text-ink-3">Try another spelling. If the company is missing, a senior&apos;s upload would add it.</p>
          </div>
        )}

        {noData.length > 0 && (
          <div className="mt-14">
            <h2 className="font-display text-xl font-bold text-ink">Awaiting verified data</h2>
            <p className="mt-1 text-sm text-ink-3">These companies have uploads under review or only unverified public sources.</p>
            <div className="mt-5 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
              {noData.map((c, i) => <CompanyCardView key={c.id} c={c} index={i} />)}
            </div>
          </div>
        )}
      </section>
    </>
  );
}
