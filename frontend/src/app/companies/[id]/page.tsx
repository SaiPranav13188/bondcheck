"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, BellRing, CalendarClock, ChevronDown, ExternalLink, FileText, GitCompareArrows, Globe, Megaphone, MessageSquareText, Quote, TrendingDown, TrendingUp, Upload } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";
import ExitCalculator from "@/components/ExitCalculator";
import RedactedText from "@/components/RedactedText";
import SubscribeModal from "@/components/SubscribeModal";
import { ConfidencePill, Disclaimer, ErrorState, Monogram, Reveal, RiskBadge, RiskMeter, Skeleton, useApi } from "@/components/ui";
import { getJSON, type CompanyDetail, type GroupStats, type OfferRecord } from "@/lib/api";
import { companyCover, dateShort, FIELD_LABELS, fieldValue, inr, inrShort, shortName } from "@/lib/format";

export default function CompanyPage() {
  const { id } = useParams<{ id: string }>();
  const { data, error, loading, reload } = useApi(() => getJSON<CompanyDetail>(`/company/${id}`), [id]);
  const batches = useMemo(() => (data ? Object.keys(data.batches).sort().reverse() : []), [data]);
  const [batchSel, setBatchSel] = useState<string | null>(null);
  const [subOpen, setSubOpen] = useState(false);
  const batch = batchSel ?? batches[0];
  const group: GroupStats | undefined = batch ? data?.batches[batch]?.all : undefined;

  if (error) return <div className="container-x py-20"><ErrorState message={error} onRetry={reload} /></div>;
  if (loading || !data) return <LoadingView />;

  const c = data.company;
  const name = shortName(c.name);
  const hasBond = !!group && (group.bond_share ?? 0) >= 0.5;

  return (
    <>
      {/* ------------------------------------------------ cover */}
      <section className="relative -mt-16 overflow-hidden pt-16">
        <div className="absolute inset-0">
          <Image src={companyCover(c.id)} alt="" fill priority sizes="100vw" className="object-cover" />
          <div className="absolute inset-0 bg-linear-to-b from-ink/80 via-ink/75 to-canvas" />
        </div>
        <div className="container-x relative pb-10 pt-8">
          <Link href="/companies" className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-300 transition hover:text-white"><ArrowLeft className="h-4 w-4" /> All companies</Link>
          <div className="mt-6 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-5">
              <Monogram id={c.id} name={c.name} size="xl" />
              <div>
                <h1 className="font-display text-3xl font-extrabold text-white sm:text-4xl">{name}</h1>
                <p className="mt-1 text-sm text-slate-300">{c.name}{c.aliases.length > 1 ? ` · also seen as ${c.aliases.filter((a) => a !== c.name).slice(0, 2).join(", ")}` : ""}</p>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <RiskBadge risk={group?.risk} size="md" />
                  <span className="rounded-full bg-white/90"><ConfidencePill level={data.confidence} uploads={data.verified_uploads} /></span>
                  {data.conflicts.length > 0 && <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-900"><GitCompareArrows className="h-3.5 w-3.5" /> {data.conflicts.length} open conflict</span>}
                </div>
              </div>
            </motion.div>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }} className="flex flex-wrap gap-2">
              <button onClick={() => setSubOpen(true)} className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-ink shadow-lg transition hover:-translate-y-0.5"><BellRing className="h-4 w-4 text-brand-600" /> Get drive alerts</button>
              <Link href={`/ask?q=${encodeURIComponent(`If I join ${name} and leave after 10 months, what could I owe?`)}`} className="inline-flex items-center gap-2 rounded-full bg-ink/80 px-5 py-2.5 text-sm font-semibold text-white ring-1 ring-white/25 backdrop-blur transition hover:bg-ink"><MessageSquareText className="h-4 w-4" /> Ask about {name.split(" ")[0]}</Link>
            </motion.div>
          </div>
        </div>
      </section>

      <div className="container-x">
        {data.data_requests.length > 0 && (
          <Reveal className="mb-6">
            <div className="flex flex-col items-start gap-3 rounded-2xl bg-linear-to-r from-amber-50 to-orange-50 p-4 ring-1 ring-amber-200 sm:flex-row sm:items-center">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-700"><Megaphone className="h-5 w-5" /></span>
              <p className="flex-1 text-sm text-amber-900"><span className="font-semibold">Data needed:</span> {data.data_requests[0].message}</p>
              <Link href="/upload" className="inline-flex items-center gap-1.5 rounded-full bg-amber-600 px-4 py-2 text-sm font-semibold text-white"><Upload className="h-4 w-4" /> Upload</Link>
            </div>
          </Reveal>
        )}

        {batches.length === 0 ? (
          <div className="card p-10 text-center">
            <FileText className="mx-auto h-10 w-10 text-slate-300" />
            <p className="mt-3 font-display text-xl font-bold text-ink">No verified uploads yet</p>
            <p className="mx-auto mt-2 max-w-md text-ink-3">{data.pending_uploads > 0 ? `${data.pending_uploads} upload(s) are waiting for a moderator. ` : ""}Until then, ask HR for the service agreement in writing before you accept.</p>
            {data.public_sources.length > 0 && <PublicSources sources={data.public_sources} />}
          </div>
        ) : (
          <>
            {/* batch tabs */}
            <div className="mb-6 flex flex-wrap items-center gap-2">
              <span className="mr-1 text-sm font-medium text-ink-3">Batch</span>
              {batches.map((b) => (
                <button key={b} onClick={() => setBatchSel(b)} className={`relative rounded-full px-4 py-2 text-sm font-semibold transition ${b === batch ? "text-white" : "bg-white text-ink-2 ring-1 ring-line hover:ring-brand-200"}`}>
                  {b === batch && <motion.span layoutId="batch-pill" className="absolute inset-0 rounded-full bg-ink" />}
                  <span className="relative">{b}</span>
                </button>
              ))}
              {data.trend && <TrendTag trend={data.trend} />}
            </div>

            {/* key tiles */}
            {group && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                <Tile label="Bond period" value={hasBond ? `${group.typical_bond_months ?? "?"} months` : "No bond"} accent={hasBond} />
                <Tile label="Penalty" value={hasBond ? inr(group.typical_penalty) : "—"} accent={hasBond} />
                <Tile label="Pro-rated?" value={!hasBond ? "—" : group.prorated === "yes" ? "Yes" : group.prorated === "no" ? "No" : "Not stated"} />
                <Tile label="Notice period" value={group.typical_notice_days ? `${group.typical_notice_days} days` : "—"} />
                <Tile label="Median CTC" value={inr(group.median_ctc)} />
                <Tile label="Certificates kept" value={`${Math.round((group.certificates_retained_share ?? 0) * 100)}% of letters`} />
              </div>
            )}

            <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_380px]">
              <div className="min-w-0 space-y-8">
                {group && <RiskCard group={group} />}
                {data.conflicts.length > 0 && <Conflicts data={data} />}
                {data.timeline.length > 0 && <PenaltyChart timeline={data.timeline} />}
                {batch && <RoleBreakdown roles={data.batches[batch].roles} />}
                <Records companyName={c.name} records={data.records.filter((r) => String(r.batch_year) === batch)} />
              </div>

              <aside className="space-y-6 lg:sticky lg:top-20 lg:self-start">
                {hasBond && group && <ExitCalculator key={`${batch}-${group.typical_penalty}-${group.typical_bond_months}`} compact penalty={group.typical_penalty ?? 100000} bondMonths={group.typical_bond_months ?? 24} prorated={group.prorated ?? "not_mentioned"} />}
                <Drives drives={data.drives} onSubscribe={() => setSubOpen(true)} />
                {data.public_sources.length > 0 && <div className="card p-5"><PublicSources sources={data.public_sources} /></div>}
                <div className="relative overflow-hidden rounded-2xl">
                  <Image src="/images/documents.jpg" alt="" fill sizes="380px" className="object-cover" />
                  <div className="absolute inset-0 bg-linear-to-br from-brand-800/95 to-ink/90" />
                  <div className="relative p-6">
                    <p className="font-display text-lg font-bold text-white">Joined {name.split(" ")[0]}?</p>
                    <p className="mt-1 text-sm text-brand-100">Your letter makes this page more reliable for every junior after you.</p>
                    <Link href="/upload" className="mt-4 inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-ink"><Upload className="h-4 w-4" /> Upload anonymously</Link>
                  </div>
                </div>
                <Disclaimer />
              </aside>
            </div>
          </>
        )}
      </div>
      <SubscribeModal open={subOpen} onClose={() => setSubOpen(false)} companyId={c.id} companyName={name} />
    </>
  );
}

// ------------------------------------------------------------------ pieces
function Tile({ label, value, accent = false }: { label: string; value: string; accent?: boolean }) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className={`rounded-2xl p-4 ring-1 ${accent ? "bg-white ring-brand-200 shadow-[0_10px_30px_-15px_rgba(79,70,229,0.45)]" : "bg-white ring-line"}`}>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-3">{label}</p>
      <p className={`mt-1 font-display text-lg font-bold ${accent ? "text-brand-700" : "text-ink"}`}>{value}</p>
    </motion.div>
  );
}

function TrendTag({ trend }: { trend: NonNullable<CompanyDetail["trend"]> }) {
  if (trend.direction === "unchanged") return null;
  const harsher = trend.direction === "harsher";
  const Icon = harsher ? TrendingUp : TrendingDown;
  return (
    <span className={`ml-auto inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold ring-1 ${harsher ? "bg-rose-50 text-rose-700 ring-rose-200" : "bg-emerald-50 text-emerald-700 ring-emerald-200"}`}>
      <Icon className="h-4 w-4" /> Penalty {harsher ? "up" : "down"} {inr(Math.abs(trend.penalty_change))} since {trend.from_batch}
    </span>
  );
}

function RiskCard({ group }: { group: GroupStats }) {
  return (
    <Reveal>
      <div className="card flex flex-col gap-6 p-6 sm:flex-row sm:items-center">
        <RiskMeter risk={group.risk} size={120} stroke={10} showLabel />
        <div className="flex-1">
          <h2 className="font-display text-xl font-bold text-ink">Why this score</h2>
          <p className="mt-1 text-sm text-ink-3">An explainable 0 to 100 score from {group.uploads} verified letter{group.uploads === 1 ? "" : "s"}. Higher means a costlier exit.</p>
          <ul className="mt-4 flex flex-wrap gap-2">
            {group.risk.factors.map((f) => <li key={f} className="rounded-lg bg-slate-100 px-2.5 py-1.5 text-sm text-ink-2">{f}</li>)}
          </ul>
          {group.risky_clauses.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-semibold uppercase tracking-wide text-ink-3">Other clauses reported</p>
              <ul className="mt-2 space-y-1.5">
                {group.risky_clauses.map((r) => (
                  <li key={r.clause} className="flex items-center justify-between gap-3 text-sm">
                    <span className="text-ink-2 first-letter:uppercase">{r.clause}</span>
                    <span className="shrink-0 text-ink-3">{r.count} of {group.uploads} letters</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </Reveal>
  );
}

function Conflicts({ data }: { data: CompanyDetail }) {
  return (
    <Reveal>
      <div className="overflow-hidden rounded-[1.25rem] bg-white ring-1 ring-amber-200">
        <div className="flex items-center gap-3 bg-amber-50 px-6 py-4">
          <GitCompareArrows className="h-5 w-5 text-amber-700" />
          <div>
            <h2 className="font-display font-bold text-amber-900">Uploads disagree</h2>
            <p className="text-sm text-amber-800">Letters for the same batch and role report different terms. Shown openly while a moderator reviews.</p>
          </div>
        </div>
        <div className="space-y-6 p-6">
          {data.conflicts.map((cf) => {
            const total = Object.values(cf.values_seen).reduce((a, b) => a + b, 0);
            const entries = Object.entries(cf.values_seen).sort((a, b) => b[1] - a[1]);
            return (
              <div key={cf.id}>
                <p className="text-sm font-semibold text-ink">{FIELD_LABELS[cf.field] ?? cf.field} · {cf.batch_year}{cf.role ? ` · ${cf.role}` : ""}</p>
                <div className="mt-3 space-y-2.5">
                  {entries.map(([v, n], i) => (
                    <div key={v} className="flex items-center gap-3">
                      <span className="w-24 shrink-0 text-sm font-semibold text-ink">{cf.field === "penalty_amount" ? inr(Number(v)) : v}</span>
                      <div className="h-7 flex-1 overflow-hidden rounded-md bg-slate-100">
                        <motion.div initial={{ width: 0 }} whileInView={{ width: `${(n / total) * 100}%` }} viewport={{ once: true }} transition={{ duration: 0.9, delay: i * 0.1 }}
                          className="h-full rounded-r-[4px]" style={{ background: i === 0 ? "var(--series-1)" : "#94a3b8" }} />
                      </div>
                      <span className="w-20 shrink-0 text-right text-sm text-ink-2">{n} letter{n === 1 ? "" : "s"}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Reveal>
  );
}

/** Single-series bar chart: typical penalty per batch. Hover for exact values. */
function PenaltyChart({ timeline }: { timeline: CompanyDetail["timeline"] }) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(...timeline.map((t) => t.typical_penalty ?? 0), 1);
  const ticks = [0, 0.5, 1].map((f) => Math.round((max * f) / 1000) * 1000);
  return (
    <Reveal>
      <div className="card p-6">
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-xl font-bold text-ink">Typical penalty by batch</h2>
          <span className="text-xs text-ink-3">Most common value in verified uploads</span>
        </div>
        <div className="relative mt-6 flex h-56 gap-3 pl-14">
          <div className="pointer-events-none absolute inset-y-0 left-0 right-0">
            {ticks.map((t) => (
              <div key={t} className="absolute left-0 right-0 flex items-center gap-2" style={{ bottom: `${(t / max) * 100}%` }}>
                <span className="w-12 text-right text-[11px] text-ink-3">{inrShort(t)}</span>
                <span className="h-px flex-1 bg-slate-100" />
              </div>
            ))}
          </div>
          {timeline.map((t, i) => {
            const h = ((t.typical_penalty ?? 0) / max) * 100;
            return (
              <div key={t.batch} className="relative flex flex-1 flex-col items-center justify-end" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                <AnimatePresence>
                  {hover === i && (
                    <motion.div initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="absolute z-10 whitespace-nowrap rounded-xl bg-ink px-3 py-2 text-xs text-white shadow-xl" style={{ bottom: `calc(${h}% + 10px)` }}>
                      <p className="font-semibold">{t.batch} batch</p>
                      <p>Penalty {inr(t.typical_penalty)} · {t.typical_bond_months ?? 0} months</p>
                      <p className="text-slate-300">{t.uploads} uploads · median CTC {inrShort(t.median_ctc)}</p>
                    </motion.div>
                  )}
                </AnimatePresence>
                <span className="mb-1.5 text-xs font-semibold text-ink-2">{t.typical_penalty ? inrShort(t.typical_penalty) : "No bond"}</span>
                <motion.div initial={{ height: 0 }} whileInView={{ height: `${Math.max(h, 1.5)}%` }} viewport={{ once: true }} transition={{ duration: 0.9, delay: i * 0.12, ease: [0.16, 1, 0.3, 1] }}
                  className={`w-full max-w-16 rounded-t-[4px] transition-opacity ${hover !== null && hover !== i ? "opacity-50" : ""}`} style={{ background: "var(--series-1)" }} />
              </div>
            );
          })}
        </div>
        <div className="mt-2 flex gap-3 pl-14">
          {timeline.map((t) => <span key={t.batch} className="flex-1 text-center text-xs font-medium text-ink-3">{t.batch}</span>)}
        </div>
      </div>
    </Reveal>
  );
}

function RoleBreakdown({ roles }: { roles: Record<string, GroupStats> }) {
  const entries = Object.entries(roles);
  if (entries.length < 2) return null;
  return (
    <Reveal>
      <div className="card overflow-hidden">
        <h2 className="px-6 pt-6 font-display text-xl font-bold text-ink">By role</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead><tr className="border-y border-line bg-canvas text-left text-xs uppercase tracking-wide text-ink-3">
              <th className="px-6 py-3 font-semibold">Role</th><th className="px-3 py-3 font-semibold">Bond</th><th className="px-3 py-3 font-semibold">Penalty</th><th className="px-3 py-3 font-semibold">Median CTC</th><th className="px-6 py-3 text-right font-semibold">Uploads</th>
            </tr></thead>
            <tbody>
              {entries.map(([role, g]) => (
                <tr key={role} className="border-b border-line last:border-0">
                  <td className="px-6 py-3.5 font-medium text-ink">{role}</td>
                  <td className="px-3 py-3.5 text-ink-2">{g.typical_bond_months ? `${g.typical_bond_months} months` : "None"}</td>
                  <td className="px-3 py-3.5 text-ink-2">{inr(g.typical_penalty)}</td>
                  <td className="px-3 py-3.5 text-ink-2">{inr(g.median_ctc)}</td>
                  <td className="px-6 py-3.5 text-right text-ink-2">{g.uploads}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Reveal>
  );
}

function Records({ records, companyName }: { records: OfferRecord[]; companyName: string }) {
  const [open, setOpen] = useState<number | null>(records[0]?.id ?? null);
  return (
    <Reveal>
      <div className="card p-6">
        <div className="flex items-baseline justify-between">
          <h2 className="font-display text-xl font-bold text-ink">Evidence from letters</h2>
          <span className="text-xs text-ink-3">Redacted quotes, verified against each document</span>
        </div>
        <ul className="mt-5 space-y-3">
          {records.map((r) => {
            const isOpen = open === r.id;
            return (
              <li key={r.id} className={`overflow-hidden rounded-2xl ring-1 transition ${isOpen ? "ring-brand-200" : "ring-line"}`}>
                <button onClick={() => setOpen(isOpen ? null : r.id)} className="flex w-full items-center gap-4 px-4 py-3.5 text-left hover:bg-canvas">
                  <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 font-mono text-xs font-bold text-brand-700">#{r.id}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold text-ink">{r.role ?? "Role not stated"} · {r.has_bond ? `${r.bond_months ?? "?"} months, ${inr(r.penalty_amount)}` : "No bond"}</span>
                    <span className="block text-xs text-ink-3">Uploaded {dateShort(r.created_at)} · confidence {Math.round(r.confidence * 100)}%</span>
                  </span>
                  <ChevronDown className={`h-5 w-5 shrink-0 text-ink-3 transition ${isOpen ? "rotate-180" : ""}`} />
                </button>
                <AnimatePresence initial={false}>
                  {isOpen && (
                    <motion.div initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0 }} className="overflow-hidden">
                      <div className="space-y-2.5 border-t border-line bg-canvas/60 p-4">
                        {r.evidence.map((e, i) => (
                          <div key={i} className="flex gap-3 rounded-xl bg-white p-3 ring-1 ring-line">
                            <Quote className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" />
                            <div className="min-w-0">
                              <p className="text-[11px] font-semibold uppercase tracking-wide text-brand-700">{FIELD_LABELS[e.field] ?? e.field}: {e.field === "company_name" ? shortName(companyName) : fieldValue(e.field, (r as unknown as Record<string, unknown>)[e.field])}</p>
                              <p className="mt-1 text-sm leading-relaxed text-ink-2"><RedactedText text={e.quote} /></p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </li>
            );
          })}
        </ul>
      </div>
    </Reveal>
  );
}

function Drives({ drives, onSubscribe }: { drives: CompanyDetail["drives"]; onSubscribe: () => void }) {
  return (
    <div className="card p-5">
      <p className="flex items-center gap-2 font-display font-bold text-ink"><CalendarClock className="h-5 w-5 text-brand-600" /> Upcoming drives</p>
      {drives.length === 0 ? <p className="mt-2 text-sm text-ink-3">No drives scheduled right now.</p> : (
        <ul className="mt-3 space-y-2">
          {drives.map((d) => (
            <li key={d.id} className="flex items-center justify-between rounded-xl bg-canvas px-3 py-2.5 text-sm">
              <span className="font-medium text-ink">{d.college}</span>
              <span className="text-ink-3">{dateShort(d.drive_date)}</span>
            </li>
          ))}
        </ul>
      )}
      <button onClick={onSubscribe} className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-ink py-2.5 text-sm font-semibold text-white transition hover:bg-brand-700"><BellRing className="h-4 w-4" /> Alert me 7 days before</button>
    </div>
  );
}

function PublicSources({ sources }: { sources: CompanyDetail["public_sources"] }) {
  return (
    <div className="mt-2 text-left">
      <p className="flex items-center gap-2 font-display font-bold text-ink"><Globe className="h-5 w-5 text-slate-500" /> Public sources</p>
      <p className="mt-1 inline-flex rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">Unverified public source</p>
      <ul className="mt-3 space-y-2">
        {sources.map((s) => (
          <li key={s.id} className="rounded-xl bg-canvas p-3 text-sm">
            <p className="text-ink-2">{s.summary ?? "No summary"}</p>
            <a href={s.source_url} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-brand-700">{new URL(s.source_url).hostname} <ExternalLink className="h-3 w-3" /></a>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LoadingView() {
  return (
    <div className="container-x space-y-6 py-16">
      <div className="flex items-center gap-5"><Skeleton className="h-20 w-20 rounded-3xl" /><div className="space-y-3"><Skeleton className="h-8 w-72" /><Skeleton className="h-4 w-48" /></div></div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-20" />)}</div>
      <div className="grid gap-8 lg:grid-cols-[1fr_380px]"><Skeleton className="h-96" /><Skeleton className="h-96" /></div>
    </div>
  );
}
