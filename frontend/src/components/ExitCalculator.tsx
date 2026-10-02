"use client";

import { motion } from "framer-motion";
import { Calculator, Info } from "lucide-react";
import { useEffect, useState } from "react";
import { postJSON } from "@/lib/api";
import { inr } from "@/lib/format";

type Result = { amount: number | null; explanation: string; formula: string | null; remaining_months?: number };

export default function ExitCalculator({ penalty: p0 = 150000, bondMonths: b0 = 24, prorated: pr0 = "not_mentioned", compact = false }: { penalty?: number; bondMonths?: number; prorated?: string; compact?: boolean }) {
  const [penalty, setPenalty] = useState(p0);
  const [bond, setBond] = useState(b0);
  const [served, setServed] = useState(Math.min(10, b0));
  const [prorated, setProrated] = useState(pr0);
  const [res, setRes] = useState<Result | null>(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => {
      postJSON<Result>("/calc/exit-cost", { penalty, bond_months: bond, months_served: served, prorated })
        .then((r) => { setRes(r); setErr(false); })
        .catch(() => setErr(true));
    }, 120);
    return () => clearTimeout(t);
  }, [penalty, bond, served, prorated]);

  const pct = bond ? Math.min(100, (served / bond) * 100) : 0;
  const owePct = res?.amount != null && penalty ? (res.amount / penalty) * 100 : 0;

  return (
    <div className={`card overflow-hidden ${compact ? "" : "p-1"}`}>
      <div className={`grid gap-6 ${compact ? "p-5" : "p-5 sm:p-7 lg:grid-cols-[1.1fr_1fr]"}`}>
        <div className="space-y-5">
          <div className="flex items-center gap-2.5">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-brand-50 text-brand-600"><Calculator className="h-5 w-5" /></span>
            <div>
              <p className="font-display font-bold text-ink">Exit-cost calculator</p>
              <p className="text-xs text-ink-3">Computed by plain Python on the server, never by the AI</p>
            </div>
          </div>
          <Slider label="Bond penalty" value={penalty} min={10000} max={500000} step={5000} display={inr(penalty)} onChange={setPenalty} />
          <Slider label="Bond period" value={bond} min={6} max={48} step={1} display={`${bond} months`} onChange={(v) => { setBond(v); setServed((s) => Math.min(s, v)); }} />
          <Slider label="You leave after" value={served} min={0} max={bond} step={1} display={`${served} months`} onChange={setServed} accent />
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-3">Is the penalty pro-rated?</p>
            <div className="grid grid-cols-3 gap-1.5 rounded-xl bg-slate-100 p-1">
              {[["yes", "Yes"], ["no", "No"], ["not_mentioned", "Not stated"]].map(([v, l]) => (
                <button key={v} onClick={() => setProrated(v)} className={`relative rounded-lg py-2 text-sm font-medium transition ${prorated === v ? "text-ink" : "text-ink-3 hover:text-ink-2"}`}>
                  {prorated === v && <motion.span layoutId={`pr-${compact}`} className="absolute inset-0 rounded-lg bg-white shadow-sm" />}
                  <span className="relative">{l}</span>
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="relative flex flex-col justify-between overflow-hidden rounded-2xl bg-linear-to-br from-ink via-brand-900 to-brand-800 p-6 text-white">
          <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-fuchsia-500/30 blur-3xl" />
          <div className="relative">
            <p className="text-sm text-brand-200">You could owe</p>
            <motion.p key={res?.amount ?? "x"} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-1 font-display text-4xl font-extrabold tracking-tight sm:text-5xl">
              {err ? "—" : inr(res?.amount ?? null)}
            </motion.p>
            <div className="mt-5 space-y-2">
              <div className="flex justify-between text-xs text-brand-200"><span>Bond served</span><span>{Math.round(pct)}%</span></div>
              <div className="h-2.5 overflow-hidden rounded-full bg-white/10">
                <motion.div className="h-full rounded-full bg-linear-to-r from-emerald-400 to-teal-300" animate={{ width: `${pct}%` }} transition={{ type: "spring", stiffness: 120, damping: 20 }} />
              </div>
              <div className="flex justify-between pt-1 text-xs text-brand-200"><span>Share of penalty owed</span><span>{Math.round(owePct)}%</span></div>
              <div className="h-2.5 overflow-hidden rounded-full bg-white/10">
                <motion.div className="h-full rounded-full bg-linear-to-r from-amber-300 to-rose-400" animate={{ width: `${owePct}%` }} transition={{ type: "spring", stiffness: 120, damping: 20 }} />
              </div>
            </div>
          </div>
          <p className="relative mt-5 flex gap-2 text-sm leading-relaxed text-brand-100">
            <Info className="mt-0.5 h-4 w-4 shrink-0" />
            {err ? "Start the API to use the calculator." : res?.explanation}
          </p>
        </div>
      </div>
    </div>
  );
}

function Slider({ label, value, min, max, step, display, onChange, accent = false }: { label: string; value: number; min: number; max: number; step: number; display: string; onChange: (v: number) => void; accent?: boolean }) {
  const pct = max > min ? ((value - min) / (max - min)) * 100 : 0;
  return (
    <label className="block">
      <span className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-semibold uppercase tracking-wide text-ink-3">{label}</span>
        <span className={`font-display text-base font-bold ${accent ? "text-brand-600" : "text-ink"}`}>{display}</span>
      </span>
      <input
        type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="h-2 w-full cursor-pointer appearance-none rounded-full outline-none [&::-webkit-slider-thumb]:h-5 [&::-webkit-slider-thumb]:w-5 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-4 [&::-webkit-slider-thumb]:border-white [&::-webkit-slider-thumb]:bg-brand-600 [&::-webkit-slider-thumb]:shadow-md [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-4 [&::-moz-range-thumb]:border-white [&::-moz-range-thumb]:bg-brand-600"
        style={{ background: `linear-gradient(to right, #6366f1 ${pct}%, #e5e8f0 ${pct}%)` }}
      />
    </label>
  );
}
