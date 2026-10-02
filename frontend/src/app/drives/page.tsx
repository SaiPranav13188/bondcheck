"use client";

import { motion } from "framer-motion";
import { BellRing, CalendarDays, CheckCircle2, Clock, Megaphone, Upload } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ErrorState, Monogram, Reveal, Skeleton, useApi } from "@/components/ui";
import { getJSON, postJSON, type Drive } from "@/lib/api";
import { dateShort, relativeDays, shortName } from "@/lib/format";

type DataRequest = { id: number; company_id: number; name: string; message: string; reason: string; created_at: string };

export default function DrivesPage() {
  const drives = useApi(() => getJSON<Drive[]>("/drives?days=60"));
  const requests = useApi(() => getJSON<DataRequest[]>("/data-requests"));
  const [selected, setSelected] = useState<number[]>([]);
  const [email, setEmail] = useState("");
  const [all, setAll] = useState(false);
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");

  const companies = useMemo(() => {
    const m = new Map<number, Drive>();
    drives.data?.forEach((d) => { if (!m.has(d.company_id)) m.set(d.company_id, d); });
    return [...m.values()];
  }, [drives.data]);

  const toggle = (id: number) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const subscribe = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("saving");
    try {
      await postJSON("/subscribe", { email, company_ids: selected, alert_all: all });
      setState("done");
    } catch {
      setState("error");
    }
  };

  return (
    <>
      <section className="relative -mt-16 overflow-hidden pb-28 pt-32">
        <Image src="/images/classroom.jpg" alt="" fill priority sizes="100vw" className="object-cover" />
        <div className="absolute inset-0 bg-linear-to-br from-ink/95 via-brand-900/85 to-fuchsia-900/60" />
        <div className="container-x relative">
          <Reveal>
            <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-brand-100 ring-1 ring-white/20"><CalendarDays className="h-3.5 w-3.5" /> Placement season</p>
            <h1 className="mt-4 max-w-3xl font-display text-4xl font-extrabold text-white sm:text-5xl">Upcoming drives, with the bond terms you&apos;ll be asked to sign.</h1>
            <p className="mt-4 max-w-xl text-lg text-slate-300">The Monitor Agent checks every drive in the next 30 days daily. The Alert Agent warns subscribers a week ahead.</p>
          </Reveal>
        </div>
      </section>

      <div className="container-x relative -mt-16 grid gap-8 lg:grid-cols-[1fr_400px]">
        {/* timeline */}
        <div className="card p-6 sm:p-8">
          <h2 className="font-display text-xl font-bold text-ink">Next 60 days</h2>
          {drives.error && <div className="mt-6"><ErrorState message={drives.error} onRetry={drives.reload} /></div>}
          <ol className="relative mt-6 space-y-4 before:absolute before:bottom-3 before:left-[27px] before:top-3 before:w-0.5 before:bg-linear-to-b before:from-brand-300 before:to-slate-100">
            {drives.loading && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24" />)}
            {drives.data?.map((d, i) => (
              <motion.li key={d.id} initial={{ opacity: 0, x: -16 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }} className="relative flex gap-4">
                <div className={`relative z-10 grid h-14 w-14 shrink-0 place-items-center rounded-2xl text-center ring-4 ring-white ${d.days_left <= 7 ? "bg-rose-500 text-white" : "bg-ink text-white"}`}>
                  <span><span className="block font-display text-lg font-bold leading-none">{d.days_left}</span><span className="text-[9px] font-semibold uppercase tracking-wider opacity-80">days</span></span>
                  {d.days_left <= 7 && <span className="absolute inset-0 animate-pulse-ring rounded-2xl bg-rose-400/50" />}
                </div>
                <Link href={`/companies/${d.company_id}`} className="flex flex-1 flex-col gap-3 rounded-2xl p-4 ring-1 ring-line transition hover:bg-canvas hover:ring-brand-200 sm:flex-row sm:items-center">
                  <Monogram id={d.company_id} name={d.name} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="font-semibold text-ink">{shortName(d.name)}</p>
                    <p className="text-sm text-ink-3">{d.college} · {dateShort(d.drive_date)} ({relativeDays(d.days_left)})</p>
                  </div>
                  <Coverage d={d} />
                </Link>
              </motion.li>
            ))}
          </ol>
        </div>

        {/* subscribe */}
        <div className="space-y-6 lg:sticky lg:top-20 lg:self-start">
          <div className="card overflow-hidden">
            <div className="relative h-36">
              <Image src="/images/grad-cap.jpg" alt="" fill sizes="400px" className="object-cover" />
              <div className="absolute inset-0 bg-linear-to-t from-white via-white/30 to-transparent" />
            </div>
            <div className="-mt-8 p-6 pt-0">
              <span className="relative grid h-12 w-12 place-items-center rounded-2xl bg-brand-600 text-white shadow-lg"><BellRing className="h-6 w-6" /></span>
              {state === "done" ? (
                <div className="py-6">
                  <CheckCircle2 className="h-10 w-10 text-emerald-500" />
                  <p className="mt-3 font-display text-xl font-bold text-ink">You&apos;re on the list</p>
                  <p className="mt-1 text-ink-3">Alerts arrive 7 days before each selected drive.</p>
                </div>
              ) : (
                <form onSubmit={subscribe}>
                  <h3 className="mt-4 font-display text-xl font-bold text-ink">Get warned a week ahead</h3>
                  <p className="mt-1 text-sm text-ink-3">Pick the companies visiting your campus.</p>
                  <div className="mt-4 flex max-h-56 flex-wrap gap-2 overflow-y-auto">
                    {companies.map((c) => (
                      <button type="button" key={c.company_id} onClick={() => toggle(c.company_id)}
                        className={`rounded-full px-3 py-1.5 text-sm font-medium ring-1 transition ${selected.includes(c.company_id) ? "bg-brand-600 text-white ring-brand-600" : "bg-white text-ink-2 ring-line hover:ring-brand-300"}`}>
                        {shortName(c.name)}
                      </button>
                    ))}
                  </div>
                  <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@college.edu" className="mt-4 h-12 w-full rounded-xl bg-canvas px-4 outline-none ring-1 ring-line focus:ring-2 focus:ring-brand-300" />
                  <label className="mt-3 flex items-start gap-2.5 text-sm text-ink-2">
                    <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} className="mt-0.5 h-4 w-4 accent-brand-600" /> Include “no bond” alerts too
                  </label>
                  {state === "error" && <p className="mt-2 text-sm text-rose-600">Couldn&apos;t subscribe. Check the email and try again.</p>}
                  <button disabled={!selected.length || state === "saving"} className="mt-4 w-full rounded-xl bg-ink py-3 font-semibold text-white transition hover:bg-brand-700 disabled:opacity-40">
                    {state === "saving" ? "Saving…" : `Subscribe to ${selected.length || ""} compan${selected.length === 1 ? "y" : "ies"}`}
                  </button>
                </form>
              )}
            </div>
          </div>

          {(requests.data?.length ?? 0) > 0 && (
            <div className="card p-6">
              <p className="flex items-center gap-2 font-display font-bold text-ink"><Megaphone className="h-5 w-5 text-amber-600" /> Seniors, we need you</p>
              <p className="mt-1 text-sm text-ink-3">Requests created by the Monitor Agent for drives with missing data.</p>
              <ul className="mt-4 space-y-3">
                {requests.data!.map((r) => (
                  <li key={r.id} className="rounded-xl bg-amber-50 p-3.5 text-sm text-amber-900 ring-1 ring-amber-200">{r.message}</li>
                ))}
              </ul>
              <Link href="/upload" className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-brand-700"><Upload className="h-4 w-4" /> Upload a letter</Link>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

function Coverage({ d }: { d: Drive }) {
  const g = d.coverage.gap;
  if (!g) return <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-200"><CheckCircle2 className="h-3.5 w-3.5" /> {d.coverage.uploads} verified uploads</span>;
  const map = {
    no_data: ["No verified data yet", "bg-slate-100 text-ink-2 ring-slate-200"],
    stale: [`Latest data: ${d.coverage.latest_batch} batch`, "bg-amber-50 text-amber-800 ring-amber-200"],
    conflict: ["Uploads disagree", "bg-amber-50 text-amber-800 ring-amber-200"],
  } as const;
  return <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ring-1 ${map[g][1]}`}><Clock className="h-3.5 w-3.5" /> {map[g][0]}</span>;
}
