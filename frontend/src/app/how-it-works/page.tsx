"use client";

import { motion } from "framer-motion";
import { AlertOctagon, ArrowRight, Bot, Brain, CalendarClock, Calculator, CheckCircle2, Database, EyeOff, FileQuestion, FileSearch, Gauge, Layers, Lock, MessageSquareText, Quote, Repeat, Scale, ShieldCheck, Upload, XCircle } from "lucide-react";
import Image from "next/image";
import AgentPipeline from "@/components/AgentPipeline";
import { Reveal, SectionHeading, Skeleton, useApi } from "@/components/ui";
import { getJSON } from "@/lib/api";

type EvalResults = {
  generated_at: string;
  engine: string;
  extraction: {
    letters: number; processed: number; skipped_scanned: number;
    accuracy: { single_pass: number; agentic: number; agentic_confirmed: number };
    hallucinated_fields: { single_pass: number; agentic: number };
    privacy: { pii_items: number; leaked_in_stored_records: number; stored_leak_rate: number; redacted_text_leak_rate: number };
    uploader_questions: { total: number; letters_with_questions: number };
    cost: { avg_seconds_per_letter: number; avg_tokens_per_letter: number };
  };
  conflicts_qa: { conflicts: { precision: number; recall: number; expected: number }; qa: { citation_accuracy: number; questions: number } };
};

const WORKFLOWS = [
  { icon: Upload, title: "A · New upload", color: "from-indigo-500 to-violet-600", steps: ["Privacy Agent", "Extraction (self-check loop)", "Uploader confirms uncertain fields", "Verification Agent", "Database or moderation queue", "Document deleted"] },
  { icon: MessageSquareText, title: "B · Student question", color: "from-fuchsia-500 to-pink-600", steps: ["Q&A Agent", "find_company", "Read-only SQL", "Exit-cost calculator", "Cited answer"] },
  { icon: CalendarClock, title: "C · Daily monitoring", color: "from-amber-500 to-orange-600", steps: ["Monitor Agent", "Drives in next 30 days", "Find missing / stale / conflicting data", "Public sources (labelled unverified)", "Alert Agent emails subscribers"] },
];

const GUARDRAILS = [
  { icon: EyeOff, risk: "Personal data leak", fix: "Redact → independent re-scan → redact again; reject after 3 failures. Documents never stored." },
  { icon: Quote, risk: "Made-up values", fix: "Every field needs a quote that verify_quote() finds in the document, or it is dropped." },
  { icon: Calculator, risk: "Wrong arithmetic", fix: "Exit costs computed by Python, never by the model." },
  { icon: Database, risk: "Dangerous SQL", fix: "Read-only role, SELECT only, table allow-list, automatic LIMIT, query timeout." },
  { icon: FileQuestion, risk: "Fake or malicious uploads", fix: "Document-type check, outlier detection and a human moderation queue." },
  { icon: AlertOctagon, risk: "Instructions hidden in letters", fix: "Letter text is data only; agents never follow instructions found inside it." },
  { icon: Gauge, risk: "Misleading answers", fix: "Citations, confidence and dates on every answer; conflicts shown openly." },
  { icon: Repeat, risk: "Runaway agents", fix: "Max 2 retries per agent, token budget per run, every step logged." },
  { icon: Scale, risk: "Legal liability", fix: "Clear “not legal advice” notice; terms shown as reported, not as claims." },
];

export default function HowItWorks() {
  const ev = useApi(() => getJSON<EvalResults>("/eval/results"));
  return (
    <>
      <section className="relative -mt-16 overflow-hidden bg-ink pb-24 pt-36">
        <Image src="/images/coding.jpg" alt="" fill priority sizes="100vw" className="object-cover opacity-20" />
        <div className="absolute inset-0 bg-linear-to-b from-ink/40 via-ink/80 to-ink" />
        <div className="pointer-events-none absolute left-1/2 top-20 h-96 w-[50rem] -translate-x-1/2 rounded-full bg-brand-600/30 blur-3xl" />
        <div className="container-x relative text-center">
          <Reveal>
            <p className="mx-auto inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-brand-100 ring-1 ring-white/20"><Brain className="h-3.5 w-3.5" /> Architecture</p>
            <h1 className="mx-auto mt-5 max-w-3xl font-display text-4xl font-extrabold text-white sm:text-6xl">Why this is <span className="text-gradient">agentic</span>, not just an LLM app.</h1>
            <p className="mx-auto mt-5 max-w-2xl text-lg text-slate-300">A normal LLM app takes one prompt and returns one response. BondCheck&apos;s agents plan, use tools, check their own work, make decisions, recover from errors, and act without being asked.</p>
          </Reveal>
          <div className="mt-16 text-left"><AgentPipeline dark /></div>
        </div>
      </section>

      {/* workflows */}
      <section className="container-x py-20">
        <SectionHeading eyebrow="Three workflows" title="One Orchestrator, three kinds of events" sub="Built as a LangGraph state graph: conditional routing, retry loops, checkpoints and a pause for human confirmation." />
        <div className="mt-12 grid gap-6 lg:grid-cols-3">
          {WORKFLOWS.map((w, i) => (
            <Reveal key={w.title} delay={i * 0.1}>
              <div className="card h-full p-6">
                <span className={`grid h-12 w-12 place-items-center rounded-2xl bg-linear-to-br text-white shadow-lg ${w.color}`}><w.icon className="h-6 w-6" /></span>
                <h3 className="mt-4 font-display text-xl font-bold text-ink">{w.title}</h3>
                <ol className="mt-5 space-y-0">
                  {w.steps.map((s, j) => (
                    <motion.li key={s} initial={{ opacity: 0, x: -10 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.2 + j * 0.08 }} className="relative flex gap-3 pb-4 last:pb-0">
                      {j < w.steps.length - 1 && <span className="absolute left-[11px] top-6 h-full w-0.5 bg-slate-100" />}
                      <span className="relative grid h-6 w-6 shrink-0 place-items-center rounded-full bg-brand-50 text-[11px] font-bold text-brand-700 ring-1 ring-brand-100">{j + 1}</span>
                      <span className="pt-0.5 text-sm text-ink-2">{s}</span>
                    </motion.li>
                  ))}
                </ol>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* self-verification */}
      <section className="container-x pb-20">
        <div className="grid items-center gap-10 lg:grid-cols-2">
          <Reveal className="relative h-[420px] overflow-hidden rounded-[2rem]">
            <Image src="/images/documents.jpg" alt="Documents and a calculator on a desk" fill sizes="(min-width: 1024px) 50vw, 100vw" className="object-cover" />
            <div className="absolute inset-0 bg-linear-to-tr from-ink/70 to-transparent" />
            <div className="absolute bottom-6 left-6 right-6 rounded-2xl bg-white/95 p-4 font-mono text-xs shadow-xl backdrop-blur">
              <p className="text-ink-3">extraction · round 1</p>
              <p className="mt-1 text-rose-600">✗ bond_months = 6 · quote is about probation</p>
              <p className="text-amber-600">↻ re-reading the bond section…</p>
              <p className="text-emerald-600">✓ bond_months = 24 · “serve the Company for a minimum period of 24 months”</p>
            </div>
          </Reveal>
          <div>
            <SectionHeading eyebrow="The core agentic behaviour" title="An extraction loop that checks its own work" />
            <ul className="mt-8 space-y-4">
              {[
                [FileSearch, "Extract with evidence", "All 12 fields, each with a verbatim quote and a confidence score."],
                [CheckCircle2, "Verify every quote", "verify_quote() confirms the quote exists, and the value is re-derived from it with deterministic normalisers."],
                [ShieldCheck, "Check relevance and consistency", "A probation clause isn't a bond; a salary isn't a penalty; a bond needs a period or a penalty."],
                [Repeat, "Re-read and retry", "Failing fields get a focused re-read of just their section, with the failure as feedback (max 2)."],
                [MessageSquareText, "Ask a human", "Anything still uncertain becomes a one-line question to the uploader."],
              ].map(([I, t, d], i) => {
                const Icon = I as typeof Bot;
                return (
                  <Reveal key={t as string} delay={i * 0.06}>
                    <li className="flex gap-4">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600"><Icon className="h-5 w-5" /></span>
                      <div><p className="font-semibold text-ink">{t as string}</p><p className="text-sm text-ink-2">{d as string}</p></div>
                    </li>
                  </Reveal>
                );
              })}
            </ul>
          </div>
        </div>
      </section>

      {/* evaluation */}
      <section id="evaluation" className="scroll-mt-20 bg-white py-20">
        <div className="container-x">
          <SectionHeading eyebrow="Evaluation" title="Single-pass extraction vs. the agentic loop" sub="The same letters, the same extractor. The only difference is the self-check and re-read loop." />
          {ev.loading && <Skeleton className="mt-10 h-80" />}
          {ev.error && <p className="mt-10 rounded-2xl bg-canvas p-6 text-ink-3">Run <code className="rounded bg-white px-1.5">python -m eval.run_eval</code> on the backend to generate results.</p>}
          {ev.data && <EvalView r={ev.data} />}
        </div>
      </section>

      {/* guardrails */}
      <section id="guardrails" className="container-x scroll-mt-20 py-20">
        <SectionHeading eyebrow="Guardrails & safety" title="Built to be trusted with someone's offer letter" />
        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {GUARDRAILS.map((g, i) => (
            <Reveal key={g.risk} delay={(i % 3) * 0.08}>
              <div className="card group h-full p-5 transition hover:-translate-y-1">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-rose-50 text-rose-600 transition group-hover:bg-emerald-50 group-hover:text-emerald-600"><g.icon className="h-5 w-5" /></span>
                <p className="mt-4 font-semibold text-ink">{g.risk}</p>
                <p className="mt-1 text-sm leading-relaxed text-ink-2">{g.fix}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* stack */}
      <section className="container-x pb-10">
        <Reveal>
          <div className="card grid gap-6 p-8 md:grid-cols-4">
            {[
              [Layers, "LangGraph", "Stateful graph, routing, retries, checkpoints, interrupts"],
              [Bot, "Claude API", "Haiku for classification and PII; Sonnet for extraction and Q&A"],
              [Database, "PostgreSQL", "Neon / Supabase; SQLite for local runs"],
              [Lock, "FastAPI + Next.js", "Streaming NDJSON agent events to this UI"],
            ].map(([I, t, d]) => {
              const Icon = I as typeof Bot;
              return (
                <div key={t as string}>
                  <Icon className="h-6 w-6 text-brand-600" />
                  <p className="mt-3 font-display font-bold text-ink">{t as string}</p>
                  <p className="mt-1 text-sm text-ink-3">{d as string}</p>
                </div>
              );
            })}
          </div>
        </Reveal>
      </section>
    </>
  );
}

function EvalView({ r }: { r: EvalResults }) {
  const x = r.extraction;
  const cq = r.conflicts_qa;
  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
  const bars = [
    { label: "Field accuracy", a: x.accuracy.single_pass, b: x.accuracy.agentic, fmt: pct, max: 1 },
    { label: "Hallucinated fields", a: x.hallucinated_fields.single_pass, b: x.hallucinated_fields.agentic, fmt: (v: number) => String(v), max: Math.max(x.hallucinated_fields.single_pass, 1) },
  ];
  const targets = [
    ["Field-level extraction accuracy", "≥ 90%", pct(x.accuracy.agentic), x.accuracy.agentic >= 0.9],
    ["PII leak rate (stored records)", "0%", pct(x.privacy.stored_leak_rate), x.privacy.stored_leak_rate === 0],
    ["Hallucinated values stored", "0", String(x.hallucinated_fields.agentic), x.hallucinated_fields.agentic === 0],
    ["Conflict detection precision / recall", "≥ 85%", `${pct(cq.conflicts.precision)} / ${pct(cq.conflicts.recall)}`, cq.conflicts.precision >= 0.85 && cq.conflicts.recall >= 0.85],
    ["Q&A answers with correct citations", "≥ 95%", pct(cq.qa.citation_accuracy), cq.qa.citation_accuracy >= 0.95],
    ["Average cost and time per upload", "measured", `${x.cost.avg_tokens_per_letter} tokens · ${x.cost.avg_seconds_per_letter}s`, true],
  ] as const;

  return (
    <div className="mt-12 grid gap-8 lg:grid-cols-[1.1fr_1fr]">
      <Reveal>
        <div className="card p-6 sm:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="font-display text-lg font-bold text-ink">Measured on {x.processed} synthetic letters</p>
            <div className="flex items-center gap-4 text-sm text-ink-2" aria-label="Legend">
              <span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: "var(--series-1)" }} /> Single-pass</span>
              <span className="inline-flex items-center gap-1.5"><span className="h-3 w-3 rounded-sm" style={{ background: "var(--series-2)" }} /> Agentic loop</span>
            </div>
          </div>
          <div className="mt-8 space-y-8">
            {bars.map((b) => (
              <div key={b.label}>
                <p className="text-sm font-semibold text-ink">{b.label}</p>
                {[["Single-pass", b.a, "var(--series-1)"], ["Agentic loop", b.b, "var(--series-2)"]].map(([name, v, color], i) => (
                  <div key={name as string} className="mt-2 flex items-center gap-3" title={`${name}: ${b.fmt(v as number)}`}>
                    <span className="w-24 shrink-0 text-xs text-ink-3">{name as string}</span>
                    <div className="h-6 flex-1 rounded-md bg-slate-50">
                      <motion.div initial={{ width: 0 }} whileInView={{ width: `${Math.max(((v as number) / b.max) * 100, 0.8)}%` }} viewport={{ once: true }} transition={{ duration: 1, delay: i * 0.15 }}
                        className="h-full rounded-r-[4px]" style={{ background: color as string }} />
                    </div>
                    <span className="w-14 shrink-0 text-right text-sm font-semibold text-ink">{b.fmt(v as number)}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
          <p className="mt-8 text-xs leading-relaxed text-ink-3">
            Engine: {r.engine}. {x.skipped_scanned > 0 && `${x.skipped_scanned} scanned letters need OCR and were skipped in this run. `}
            With uploader confirmation, accuracy reaches {pct(x.accuracy.agentic_confirmed)} ({x.uploader_questions.total} questions across {x.uploader_questions.letters_with_questions} letters).
            Test letters come from the same generator the rules were developed against, so treat this as an upper bound. Generated {r.generated_at}.
          </p>
        </div>
      </Reveal>
      <Reveal delay={0.1}>
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead><tr className="bg-canvas text-left text-xs uppercase tracking-wide text-ink-3"><th className="px-5 py-3 font-semibold">Metric</th><th className="px-3 py-3 font-semibold">Target</th><th className="px-5 py-3 text-right font-semibold">Result</th></tr></thead>
            <tbody>
              {targets.map(([m, t, v, ok]) => (
                <tr key={m} className="border-t border-line">
                  <td className="px-5 py-3.5 text-ink-2">{m}</td>
                  <td className="px-3 py-3.5 text-ink-3">{t}</td>
                  <td className="px-5 py-3.5 text-right">
                    <span className={`inline-flex items-center gap-1 font-semibold ${ok ? "text-emerald-700" : "text-rose-700"}`}>
                      {ok ? <CheckCircle2 className="h-4 w-4" /> : <XCircle className="h-4 w-4" />} {v}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-2 border-t border-line bg-canvas px-5 py-4 text-xs text-ink-3">
            <ArrowRight className="h-3.5 w-3.5" /> Reproduce with <code className="rounded bg-white px-1.5 py-0.5">python -m eval.run_eval</code>
          </div>
        </div>
      </Reveal>
    </div>
  );
}
