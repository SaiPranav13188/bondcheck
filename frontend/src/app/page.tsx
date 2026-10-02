"use client";

import { motion } from "framer-motion";
import { ArrowRight, BadgeCheck, CalendarClock, EyeOff, FileWarning, Lock, MessageSquareText, Newspaper, ScanSearch, ShieldCheck, Sparkles, Upload, Users } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import AgentPipeline from "@/components/AgentPipeline";
import CompanyCardView from "@/components/CompanyCardView";
import CompanySearch from "@/components/CompanySearch";
import ExitCalculator from "@/components/ExitCalculator";
import HeroLetter from "@/components/HeroLetter";
import { CountUp, Monogram, Reveal, SectionHeading, Skeleton, useApi } from "@/components/ui";
import { getJSON, type CompanyCard, type Drive, type Stats } from "@/lib/api";
import { inr, inrShort, relativeDays, shortName } from "@/lib/format";

export default function Home() {
  const stats = useApi(() => getJSON<Stats>("/stats"));
  const companies = useApi(() => getJSON<CompanyCard[]>("/companies?sort=risk"));
  const drives = useApi(() => getJSON<Drive[]>("/drives?days=30"));

  return (
    <>
      {/* ------------------------------------------------------------ HERO */}
      <section className="noise relative -mt-16 overflow-hidden pt-16">
        <div className="absolute inset-0 grid-bg [mask-image:radial-gradient(ellipse_at_top,black_30%,transparent_75%)]" />
        <div className="pointer-events-none absolute -left-40 top-10 h-[28rem] w-[28rem] animate-float-slow rounded-full bg-brand-300/40 blur-3xl" />
        <div className="pointer-events-none absolute -right-32 top-40 h-[26rem] w-[26rem] animate-float rounded-full bg-fuchsia-300/30 blur-3xl" />
        <div className="pointer-events-none absolute bottom-0 left-1/3 h-72 w-72 rounded-full bg-amber-200/40 blur-3xl" />

        <div className="container-x relative grid items-center gap-14 pb-20 pt-12 *:min-w-0 lg:grid-cols-[1.05fr_1fr] lg:pb-28 lg:pt-20">
          <div>
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="inline-flex items-center gap-2 rounded-full bg-white/80 py-1.5 pl-1.5 pr-4 text-sm shadow-sm ring-1 ring-slate-200 backdrop-blur">
              <span className="rounded-full bg-brand-600 px-2.5 py-0.5 text-xs font-semibold text-white">New</span>
              <span className="text-ink-2">7 AI agents now checking offer letters</span>
              <Sparkles className="h-4 w-4 text-amber-500" />
            </motion.div>
            <motion.h1 initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08, duration: 0.7 }}
              className="mt-6 font-display text-[2.6rem] font-extrabold leading-[1.05] tracking-tight text-ink sm:text-6xl lg:text-[4.2rem]">
              Know the <span className="text-gradient">bond</span><br /> before you sign.
            </motion.h1>
            <motion.p initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.16, duration: 0.7 }} className="mt-6 max-w-xl text-lg leading-relaxed text-ink-2">
              BondCheck&apos;s AI agents read anonymously uploaded offer letters, prove every bond term with a quote from the document, and warn you before the placement drive, not after you&apos;ve signed.
            </motion.p>
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.24, duration: 0.7 }} className="mt-8 max-w-xl">
              <CompanySearch large />
              <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-ink-3">
                <span className="inline-flex items-center gap-1.5"><ShieldCheck className="h-4 w-4 text-emerald-500" /> Letters never stored</span>
                <span className="inline-flex items-center gap-1.5"><BadgeCheck className="h-4 w-4 text-brand-500" /> Every value has evidence</span>
                <span className="inline-flex items-center gap-1.5"><Lock className="h-4 w-4 text-ink-3" /> Anonymous uploads</span>
              </div>
            </motion.div>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.4 }} className="mt-10 flex items-center gap-4">
              <div className="flex -space-x-3">
                {["hero-students", "study-group", "students-laptop", "classroom"].map((p) => (
                  <span key={p} className="relative h-10 w-10 overflow-hidden rounded-full ring-2 ring-white">
                    <Image src={`/images/${p}.jpg`} alt="" fill sizes="40px" className="object-cover" />
                  </span>
                ))}
              </div>
              <p className="text-sm text-ink-2">
                <span className="font-semibold text-ink">{stats.data ? <CountUp to={stats.data.verified_uploads} /> : "…"} verified letters</span> shared by seniors across {stats.data?.companies ?? "…"} companies
              </p>
            </motion.div>
          </div>
          <div className="relative px-4 sm:px-10 lg:px-4">
            <HeroLetter />
          </div>
        </div>

        {/* marquee of verified companies */}
        <div className="relative border-y border-slate-200/70 bg-white/60 py-4 backdrop-blur">
          <div className="flex overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
            <div className="flex shrink-0 animate-marquee items-center gap-10 pr-10">
              {[...(companies.data ?? []), ...(companies.data ?? [])].map((c, i) => (
                <Link href={`/companies/${c.id}`} key={`${c.id}-${i}`} className="flex shrink-0 items-center gap-2.5 opacity-70 grayscale transition hover:opacity-100 hover:grayscale-0">
                  <Monogram id={c.id} name={c.name} size="sm" />
                  <span className="whitespace-nowrap font-display text-sm font-semibold text-ink-2">{shortName(c.name)}</span>
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ STATS */}
      <section className="container-x -mt-px py-16">
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[
            { label: "Letters read by the agents", value: stats.data?.letters_processed, icon: ScanSearch, tone: "text-brand-600 bg-brand-50" },
            { label: "Personal details redacted", value: stats.data?.pii_redacted, icon: EyeOff, tone: "text-violet-600 bg-violet-50" },
            { label: "Offers that include a bond", value: stats.data ? Math.round(stats.data.bond_share * 100) : undefined, suffix: "%", icon: FileWarning, tone: "text-amber-600 bg-amber-50" },
            { label: "Highest reported penalty", value: stats.data?.max_penalty, money: true, icon: Newspaper, tone: "text-rose-600 bg-rose-50" },
          ].map((s, i) => (
            <Reveal key={s.label} delay={i * 0.08}>
              <div className="card h-full p-5 sm:p-6">
                <span className={`grid h-10 w-10 place-items-center rounded-xl ${s.tone}`}><s.icon className="h-5 w-5" /></span>
                <p className="mt-4 font-display text-3xl font-extrabold text-ink sm:text-4xl">
                  {s.value === undefined ? <Skeleton className="h-9 w-24" /> : <CountUp to={s.value} format={(n) => (s.money ? inrShort(n) : Math.round(n).toLocaleString("en-IN")) + (s.suffix ?? "")} />}
                </p>
                <p className="mt-1 text-sm text-ink-3">{s.label}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------ PROBLEM */}
      <section className="container-x py-16">
        <SectionHeading eyebrow="The problem" title={<>Lakhs of freshers sign bonds of <span className="text-rose-600">₹50,000 to ₹2,00,000</span> every year, usually blind.</>}
          sub="A commitment to stay 1 to 3 years or pay up. Students face three problems, and BondCheck is built to fix each of them." />
        <div className="mt-12 grid gap-6 md:grid-cols-3">
          {[
            { img: "signing", title: "They find out too late", text: "Bond terms usually appear after selection, when walking away is no longer realistic.", fix: "Alerts 7 days before the drive" },
            { img: "laptop", title: "Information is unreliable", text: "Blogs and forums contradict each other about the same company, with no evidence or dates.", fix: "Every term backed by a quote" },
            { img: "office", title: "Smaller firms are invisible", text: "Articles cover big IT companies, but the harshest bonds are often at firms nobody writes about.", fix: "Built from seniors' own letters" },
          ].map((p, i) => (
            <Reveal key={p.title} delay={i * 0.1}>
              <div className="card group h-full overflow-hidden">
                <div className="relative h-48 overflow-hidden">
                  <Image src={`/images/${p.img}.jpg`} alt="" fill sizes="(min-width: 768px) 33vw, 100vw" className="object-cover transition duration-700 group-hover:scale-105" />
                  <div className="absolute inset-0 bg-linear-to-t from-ink/70 via-ink/10 to-transparent" />
                  <span className="absolute bottom-3 left-4 font-display text-5xl font-extrabold text-white/90">0{i + 1}</span>
                </div>
                <div className="p-6">
                  <h3 className="font-display text-xl font-bold text-ink">{p.title}</h3>
                  <p className="mt-2 text-ink-2">{p.text}</p>
                  <p className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-sm font-semibold text-emerald-700 ring-1 ring-emerald-200">
                    <BadgeCheck className="h-4 w-4" /> {p.fix}
                  </p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------ AGENTS */}
      <section className="relative my-10 overflow-hidden bg-ink py-24">
        <Image src="/images/workshop.jpg" alt="" fill sizes="100vw" className="object-cover opacity-[0.07]" />
        <div className="pointer-events-none absolute -left-20 top-0 h-96 w-96 rounded-full bg-brand-600/30 blur-3xl" />
        <div className="pointer-events-none absolute -right-20 bottom-0 h-96 w-96 rounded-full bg-fuchsia-600/20 blur-3xl" />
        <div className="container-x relative">
          <SectionHeading light eyebrow="Agentic AI, not a chatbot" title="Seven specialised agents that plan, check their own work and act on their own."
            sub="They use tools, verify every value against the document, recover from errors, and ask a human when they aren't sure. Tap an agent to see what it does." />
          <div className="mt-14"><AgentPipeline dark /></div>
          <Reveal className="mt-12 flex flex-wrap gap-3">
            <Link href="/how-it-works" className="inline-flex items-center gap-2 rounded-full bg-white px-5 py-3 text-sm font-semibold text-ink transition hover:-translate-y-0.5">See the architecture <ArrowRight className="h-4 w-4" /></Link>
            <Link href="/upload" className="inline-flex items-center gap-2 rounded-full bg-white/10 px-5 py-3 text-sm font-semibold text-white ring-1 ring-white/20 transition hover:bg-white/15">Watch them work on a sample letter</Link>
          </Reveal>
        </div>
      </section>

      {/* ------------------------------------------------------------ RISKIEST */}
      <section className="container-x py-16">
        <div className="flex flex-col justify-between gap-6 sm:flex-row sm:items-end">
          <SectionHeading eyebrow="From verified uploads" title="Companies with the toughest bonds" sub="Ranked by an explainable risk score: bond length, penalty versus salary, pro-rating, retained certificates and other risky clauses." />
          <Reveal><Link href="/companies" className="inline-flex shrink-0 items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-ink ring-1 ring-slate-200 transition hover:ring-brand-300">All companies <ArrowRight className="h-4 w-4" /></Link></Reveal>
        </div>
        <div className="mt-10 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {companies.loading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-64" />)}
          {companies.data?.slice(0, 6).map((c, i) => <CompanyCardView key={c.id} c={c} index={i} />)}
        </div>
      </section>

      {/* ------------------------------------------------------------ DRIVES + PHOTO */}
      <section className="container-x py-16">
        <div className="grid items-stretch gap-8 lg:grid-cols-[1fr_1.1fr]">
          <Reveal className="relative min-h-[420px] overflow-hidden rounded-[2rem]">
            <Image src="/images/lecture-hall.jpg" alt="Students in a lecture hall" fill sizes="(min-width: 1024px) 45vw, 100vw" className="object-cover" />
            <div className="absolute inset-0 bg-linear-to-t from-ink via-ink/40 to-transparent" />
            <div className="absolute inset-x-0 bottom-0 p-8">
              <p className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold text-white ring-1 ring-white/25 backdrop-blur"><CalendarClock className="h-3.5 w-3.5" /> Proactive Monitor + Alert agents</p>
              <h3 className="mt-4 font-display text-3xl font-bold text-white">Warned a week before the drive, every time.</h3>
              <p className="mt-3 max-w-md text-slate-200">Subscribe to the companies visiting your campus. The Alert Agent emails you the bond terms, its confidence and the evidence 7 days before.</p>
              <Link href="/drives" className="mt-6 inline-flex items-center gap-2 rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-ink">Get alerts <ArrowRight className="h-4 w-4" /></Link>
            </div>
          </Reveal>
          <div className="card p-6 sm:p-8">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-brand-600">Next 30 days</p>
                <h3 className="mt-1 font-display text-2xl font-bold text-ink">Upcoming placement drives</h3>
              </div>
              <span className="rounded-full bg-brand-50 px-3 py-1 text-sm font-semibold text-brand-700">{drives.data?.length ?? "…"} drives</span>
            </div>
            <ul className="mt-6 space-y-3">
              {drives.loading && [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-16" />)}
              {drives.data?.slice(0, 6).map((d, i) => (
                <Reveal key={d.id} delay={i * 0.05}>
                  <Link href={`/companies/${d.company_id}`} className="flex items-center gap-4 rounded-2xl p-3 ring-1 ring-line transition hover:bg-canvas hover:ring-brand-200">
                    <div className="grid w-14 shrink-0 place-items-center rounded-xl bg-ink py-2 text-white">
                      <span className="text-[10px] font-semibold uppercase tracking-wider text-brand-200">{new Date(d.drive_date + "T00:00:00").toLocaleDateString("en-IN", { month: "short" })}</span>
                      <span className="font-display text-xl font-bold leading-none">{new Date(d.drive_date + "T00:00:00").getDate()}</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-semibold text-ink">{shortName(d.name)}</p>
                      <p className="truncate text-sm text-ink-3">{d.college} · {relativeDays(d.days_left)}</p>
                    </div>
                    <CoverageTag d={d} />
                  </Link>
                </Reveal>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ------------------------------------------------------------ CALCULATOR */}
      <section className="container-x py-16">
        <SectionHeading center eyebrow="Before you sign" title="What would leaving early actually cost?" sub="Drag the sliders. Most letters don't say whether the penalty shrinks as you serve, and that one detail can be worth a lakh." />
        <Reveal className="mt-10"><ExitCalculator /></Reveal>
      </section>

      {/* ------------------------------------------------------------ HOW YOU HELP */}
      <section className="container-x py-16">
        <div className="grid gap-6 lg:grid-cols-3">
          {[
            { icon: Upload, title: "Seniors upload", text: "Drop your offer letter. The Privacy Agent strips every personal detail before anything else happens.", img: "documents" },
            { icon: ScanSearch, title: "Agents verify", text: "Every value is proven with a quote. Disagreements between uploads are shown openly, never hidden.", img: "writing" },
            { icon: MessageSquareText, title: "Juniors ask", text: "Ask “what if I leave after 10 months?” and get a cited answer with exact arithmetic.", img: "students-laptop" },
          ].map((s, i) => (
            <Reveal key={s.title} delay={i * 0.1}>
              <div className="group relative h-80 overflow-hidden rounded-[1.75rem]">
                <Image src={`/images/${s.img}.jpg`} alt="" fill sizes="(min-width: 1024px) 33vw, 100vw" className="object-cover transition duration-700 group-hover:scale-110" />
                <div className="absolute inset-0 bg-linear-to-t from-ink/95 via-ink/50 to-ink/10" />
                <div className="absolute inset-0 flex flex-col justify-end p-7">
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-white/15 text-white ring-1 ring-white/25 backdrop-blur"><s.icon className="h-5 w-5" /></span>
                  <p className="mt-4 text-xs font-bold uppercase tracking-[0.2em] text-brand-200">Step {i + 1}</p>
                  <h3 className="mt-1 font-display text-2xl font-bold text-white">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-slate-200">{s.text}</p>
                </div>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ------------------------------------------------------------ CTA */}
      <section className="container-x pt-10">
        <Reveal>
          <div className="relative overflow-hidden rounded-[2.25rem] px-6 py-16 sm:px-14 sm:py-20">
            <Image src="/images/graduation.jpg" alt="Graduates throwing their caps" fill sizes="100vw" className="object-cover" />
            <div className="absolute inset-0 bg-linear-to-r from-brand-900/95 via-brand-800/85 to-fuchsia-900/60" />
            <div className="relative max-w-2xl">
              <p className="inline-flex items-center gap-2 rounded-full bg-white/15 px-3 py-1 text-xs font-semibold text-white ring-1 ring-white/25"><Users className="h-3.5 w-3.5" /> Pay it forward</p>
              <h2 className="mt-5 font-display text-4xl font-extrabold leading-tight text-white sm:text-5xl">Already joined? Your letter can protect your juniors.</h2>
              <p className="mt-4 text-lg text-brand-100">Two minutes, completely anonymous. The document is deleted the moment the agents finish.</p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Link href="/upload" className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3.5 font-semibold text-ink shadow-xl transition hover:-translate-y-0.5"><Upload className="h-4 w-4" /> Upload your offer letter</Link>
                <Link href="/ask" className="inline-flex items-center gap-2 rounded-full bg-white/10 px-6 py-3.5 font-semibold text-white ring-1 ring-white/30 transition hover:bg-white/20">Ask a question</Link>
              </div>
              {stats.data && <p className="mt-6 text-sm text-brand-200">Median reported penalty so far: <span className="font-semibold text-white">{inr(stats.data.median_penalty)}</span></p>}
            </div>
          </div>
        </Reveal>
      </section>
    </>
  );
}

function CoverageTag({ d }: { d: Drive }) {
  const gap = d.coverage.gap;
  const map = {
    no_data: { t: "No data yet", c: "bg-slate-100 text-ink-2 ring-slate-200" },
    stale: { t: `Only ${d.coverage.latest_batch} data`, c: "bg-amber-50 text-amber-800 ring-amber-200" },
    conflict: { t: "Conflicting", c: "bg-amber-50 text-amber-800 ring-amber-200" },
  } as const;
  const v = gap ? map[gap] : { t: `${d.coverage.uploads} uploads`, c: "bg-emerald-50 text-emerald-700 ring-emerald-200" };
  return <span className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${v.c}`}>{v.t}</span>;
}
