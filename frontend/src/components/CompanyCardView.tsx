"use client";

import { motion } from "framer-motion";
import { ArrowUpRight, CalendarClock, Files, GitCompareArrows } from "lucide-react";
import Link from "next/link";
import type { CompanyCard } from "@/lib/api";
import { dateShort, inr, shortName } from "@/lib/format";
import { ConfidencePill, Monogram, RiskMeter } from "./ui";

export default function CompanyCardView({ c, index = 0 }: { c: CompanyCard; index?: number }) {
  const s = c.summary;
  const bond = s && s.bond_share !== null && s.bond_share >= 0.5;
  return (
    <motion.div layout initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, scale: 0.96 }} transition={{ duration: 0.4, delay: Math.min(index, 8) * 0.04 }}>
      <Link href={`/companies/${c.id}`} className="card group relative flex h-full flex-col overflow-hidden p-5 transition duration-300 hover:-translate-y-1 hover:shadow-[0_20px_50px_-20px_rgba(79,70,229,0.35)]">
        <div className="pointer-events-none absolute -right-16 -top-16 h-40 w-40 rounded-full bg-brand-100/0 blur-2xl transition duration-500 group-hover:bg-brand-100/80" />
        <div className="relative flex items-start gap-3.5">
          <Monogram id={c.id} name={c.name} />
          <div className="min-w-0 flex-1">
            <h3 className="truncate font-display text-[17px] font-bold text-ink">{shortName(c.name)}</h3>
            <p className="truncate text-xs text-ink-3">{c.roles.slice(0, 2).join(" · ") || "Role not reported"}{c.latest_batch ? ` · ${c.latest_batch} batch` : ""}</p>
          </div>
          <ArrowUpRight className="h-5 w-5 text-slate-300 transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-brand-500" />
        </div>

        <div className="relative mt-5 flex items-center gap-4">
          <RiskMeter risk={s?.risk} size={64} stroke={6} />
          <div className="grid flex-1 grid-cols-2 gap-x-3 gap-y-2.5">
            <Stat label="Bond" value={!s ? "—" : bond ? `${s.typical_bond_months ?? "?"} months` : "None"} strong={!!bond} />
            <Stat label="Penalty" value={!s ? "—" : bond ? inr(s.typical_penalty) : "—"} strong={!!bond} />
            <Stat label="Median CTC" value={inr(s?.median_ctc)} />
            <Stat label="Notice" value={s?.typical_notice_days ? `${s.typical_notice_days} days` : "—"} />
          </div>
        </div>

        <div className="relative mt-5 flex flex-wrap items-center gap-2 border-t border-line pt-4">
          <ConfidencePill level={c.confidence} uploads={c.verified_uploads} />
          {c.open_conflicts > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800 ring-1 ring-amber-200"><GitCompareArrows className="h-3.5 w-3.5" /> Conflicting reports</span>
          )}
          {c.next_drive && (
            <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-100"><CalendarClock className="h-3.5 w-3.5" /> Drive {dateShort(c.next_drive)}</span>
          )}
          {c.public_sources > 0 && (
            <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-1 text-xs text-ink-2"><Files className="h-3.5 w-3.5" /> {c.public_sources} unverified source</span>
          )}
        </div>
      </Link>
    </motion.div>
  );
}

function Stat({ label, value, strong = false }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] font-medium uppercase tracking-wide text-ink-3">{label}</p>
      <p className={`truncate text-sm font-semibold ${strong ? "text-ink" : "text-ink-2"}`}>{value}</p>
    </div>
  );
}
