"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Check, CheckCircle2, CircleAlert, CircleDashed, Download, Eye, FileCheck2, FileSearch, FileText, FileUp, Loader2, Lock, MessageCircleQuestion, RotateCcw, ShieldCheck, Sparkles, Trash2, Workflow, XCircle } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import RedactedText from "@/components/RedactedText";
import { Reveal, Skeleton, useApi } from "@/components/ui";
import { API_URL, getJSON, streamEvents, type AgentEvent, type Sample, type UploadResult } from "@/lib/api";
import { DECISION_STYLE, FIELD_LABELS, fieldValue } from "@/lib/format";

const STAGES = [
  { agent: "Orchestrator", label: "Orchestrator", sub: "Reads, classifies, plans", icon: Workflow },
  { agent: "Privacy Agent", label: "Privacy", sub: "Redacts & re-scans", icon: Eye },
  { agent: "Extraction Agent", label: "Extraction", sub: "Quotes & self-checks", icon: FileSearch },
  { agent: "Verification Agent", label: "Verification", sub: "Compares & decides", icon: ShieldCheck },
];
type StageState = "idle" | "active" | "done" | "error" | "waiting";

const KIND_STYLE: Record<string, { color: string; icon: typeof Check }> = {
  start: { color: "text-sky-300", icon: CircleDashed },
  tool: { color: "text-slate-300", icon: Sparkles },
  check: { color: "text-emerald-300", icon: Check },
  retry: { color: "text-amber-300", icon: RotateCcw },
  decision: { color: "text-fuchsia-300", icon: ArrowRight },
  ask: { color: "text-amber-200", icon: MessageCircleQuestion },
  done: { color: "text-emerald-300", icon: CheckCircle2 },
  error: { color: "text-rose-300", icon: XCircle },
  info: { color: "text-slate-400", icon: ArrowRight },
};

export default function UploadPage() {
  const samples = useApi(() => getJSON<Sample[]>("/samples"));
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [batch, setBatch] = useState("");
  const [drag, setDrag] = useState(false);
  const [source, setSource] = useState<string>("");
  const logRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => { logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" }); }, [events]);

  const stageState = (agent: string): StageState => {
    const idx = STAGES.findIndex((s) => s.agent === agent);
    const seen = events.filter((e) => e.agent === agent);
    if (!seen.length) return "idle";
    if (seen.some((e) => e.kind === "error")) return "error";
    if (result?.status === "rejected" || result?.status === "escalated") {
      const lastAgentIdx = Math.max(...events.filter((e) => e.agent).map((e) => STAGES.findIndex((s) => s.agent === e.agent)));
      if (idx === lastAgentIdx || agent === "Orchestrator") return "error";
    }
    if (seen.some((e) => e.kind === "ask") && result?.status === "needs_confirmation") return "waiting";
    const later = events.some((e) => STAGES.findIndex((s) => s.agent === e.agent) > idx && e.agent !== "Orchestrator");
    if (agent === "Orchestrator") return result && result.status !== "needs_confirmation" ? "done" : "active";
    if (later || seen.some((e) => e.kind === "done" || e.kind === "decision")) return "done";
    return running ? "active" : "done";
  };

  async function run(path: string, init: RequestInit, label: string, append = false) {
    setError(null);
    setRunning(true);
    if (!append) { setEvents([]); setResult(null); }
    setSource(label);
    setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    try {
      await streamEvents(path, init, (ev) => {
        if (ev.kind === "result") setResult(ev.result as UploadResult);
        else setEvents((es) => [...es, ev]);
      });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setRunning(false);
    }
  }

  const uploadFile = () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    if (batch) fd.append("batch_year", batch);
    run("/upload", { method: "POST", body: fd }, file.name);
  };

  const confirm = (answers: Record<string, string>) => {
    if (!result) return;
    run(`/upload/${result.upload_id}/confirm`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ answers }) }, source, true);
  };

  const started = events.length > 0 || running;

  return (
    <>
      {/* header */}
      <section className="relative -mt-16 overflow-hidden pt-16">
        <Image src="/images/writing.jpg" alt="" fill priority sizes="100vw" className="object-cover" />
        <div className="absolute inset-0 bg-linear-to-r from-ink/95 via-ink/85 to-brand-900/70" />
        <div className="container-x relative grid gap-8 py-16 lg:grid-cols-[1.3fr_1fr] lg:items-center">
          <Reveal>
            <p className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold text-brand-100 ring-1 ring-white/20"><FileUp className="h-3.5 w-3.5" /> Anonymous upload</p>
            <h1 className="mt-4 font-display text-4xl font-extrabold text-white sm:text-5xl">Upload an offer letter.<br /><span className="text-brand-300">Watch the agents work.</span></h1>
            <p className="mt-4 max-w-xl text-lg text-slate-300">Every step streams live: redaction, extraction with evidence, self-correction and the final decision. The file never touches a disk.</p>
          </Reveal>
          <Reveal delay={0.1}>
            <ul className="grid gap-3 text-sm">
              {[
                [Lock, "Processed in memory only", "deleted as soon as the run ends"],
                [Eye, "Personal details removed first", "names, phone, PAN, Aadhaar, address, IDs"],
                [FileCheck2, "Only redacted clauses are kept", "as evidence for each value"],
              ].map(([Icon, t, s]) => {
                const I = Icon as typeof Lock;
                return (
                  <li key={t as string} className="flex items-center gap-3 rounded-2xl bg-white/10 p-3.5 ring-1 ring-white/15 backdrop-blur">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-400/15 text-emerald-300"><I className="h-5 w-5" /></span>
                    <span><span className="block font-semibold text-white">{t as string}</span><span className="text-slate-300">{s as string}</span></span>
                  </li>
                );
              })}
            </ul>
          </Reveal>
        </div>
      </section>

      <div className="container-x mt-10 grid gap-8 lg:grid-cols-[420px_1fr]">
        {/* ---------------------------------------------- left: inputs */}
        <div className="min-w-0 space-y-6">
          <div
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); }}
            className={`card relative overflow-hidden p-6 transition ${drag ? "ring-2 ring-brand-400" : ""}`}
          >
            <label className={`flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed px-6 py-10 text-center transition ${drag ? "border-brand-400 bg-brand-50" : "border-slate-200 hover:border-brand-300 hover:bg-canvas"}`}>
              <motion.span animate={{ y: drag ? -6 : 0 }} className="relative grid h-16 w-16 place-items-center rounded-2xl bg-linear-to-br from-brand-500 to-violet-600 text-white shadow-lg shadow-brand-500/30">
                <FileUp className="h-7 w-7" />
                <span className="absolute -right-1.5 -top-1.5 grid h-6 w-6 place-items-center rounded-full bg-emerald-400 text-white ring-2 ring-white"><Lock className="h-3 w-3" /></span>
              </motion.span>
              <span className="mt-4 font-display text-lg font-bold text-ink">{file ? file.name : "Drop your offer letter here"}</span>
              <span className="mt-1 text-sm text-ink-3">{file ? `${(file.size / 1024).toFixed(0)} KB · ready` : "PDF, scanned image or text · max 10 MB"}</span>
              <input type="file" accept=".pdf,.png,.jpg,.jpeg,.txt" className="sr-only" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            </label>
            <div className="mt-4 flex gap-3">
              <select value={batch} onChange={(e) => setBatch(e.target.value)} className="h-12 flex-1 rounded-xl bg-canvas px-3 text-sm text-ink outline-none ring-1 ring-line" aria-label="Your batch">
                <option value="">Your batch (optional)</option>
                {[2027, 2026, 2025, 2024].map((y) => <option key={y} value={y}>{y} batch</option>)}
              </select>
              {file && <button onClick={() => setFile(null)} className="grid h-12 w-12 place-items-center rounded-xl text-ink-3 ring-1 ring-line hover:text-rose-600" aria-label="Remove file"><Trash2 className="h-4 w-4" /></button>}
            </div>
            <button onClick={uploadFile} disabled={!file || running} className="mt-4 inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-ink font-semibold text-white shadow-lg transition hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-40">
              {running ? <Loader2 className="h-5 w-5 animate-spin" /> : <ShieldCheck className="h-5 w-5" />} {running ? "Agents at work…" : "Check this letter"}
            </button>
          </div>

          <div>
            <p className="font-display text-lg font-bold text-ink">No letter handy? Try a sample</p>
            <p className="text-sm text-ink-3">Synthetic letters that show off different agent behaviours.</p>
            <div className="mt-4 grid min-w-0 grid-cols-1 gap-2.5">
              {samples.loading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-16" />)}
              {samples.data?.map((s) => (
                <div key={s.key} className="group flex min-w-0 items-center gap-3 overflow-hidden rounded-2xl bg-white p-3 ring-1 ring-line transition hover:ring-brand-300">
                  <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-canvas text-brand-600"><FileText className="h-5 w-5" /></span>
                  <button disabled={running} onClick={() => run(`/samples/${s.key}/upload`, { method: "POST" }, s.title)} className="min-w-0 flex-1 text-left disabled:opacity-50">
                    <span className="block truncate text-sm font-semibold text-ink group-hover:text-brand-700">{s.title}</span>
                    <span className="block truncate text-xs text-ink-3">{s.description}</span>
                  </button>
                  <span className="hidden shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-3 sm:block">{s.expect}</span>
                  <a href={`${API_URL}/samples/${s.key}.pdf`} target="_blank" rel="noreferrer" className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-ink-3 hover:bg-canvas hover:text-ink" aria-label="View sample PDF"><Download className="h-4 w-4" /></a>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ---------------------------------------------- right: live run */}
        <div ref={panelRef} className="min-w-0 scroll-mt-24 space-y-6">
          {/* pipeline */}
          <div className="card p-5 sm:p-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-display text-lg font-bold text-ink">Live agent run</p>
                <p className="text-sm text-ink-3">{source ? source : "Upload a letter or pick a sample to start"}</p>
              </div>
              {running && <span className="inline-flex items-center gap-2 rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-700"><span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" /> streaming</span>}
            </div>
            <div className="relative mt-6 grid grid-cols-4 gap-2">
              <div className="absolute left-[12.5%] right-[12.5%] top-6 h-0.5 bg-slate-100" />
              {STAGES.map((st, i) => {
                const state = started ? stageState(st.agent) : "idle";
                return <StageNode key={st.agent} stage={st} state={state} index={i} />;
              })}
            </div>
          </div>

          {/* terminal log */}
          <div className="overflow-hidden rounded-[1.25rem] bg-[#0b1020] shadow-2xl ring-1 ring-slate-800">
            <div className="flex items-center gap-2 border-b border-white/10 px-4 py-3">
              <span className="h-3 w-3 rounded-full bg-rose-400/80" /><span className="h-3 w-3 rounded-full bg-amber-400/80" /><span className="h-3 w-3 rounded-full bg-emerald-400/80" />
              <span className="ml-3 font-mono text-xs text-slate-400">agent_runs · {result?.upload_id ?? "waiting"}</span>
            </div>
            <div ref={logRef} className="h-80 overflow-y-auto px-4 py-3 font-mono text-[12.5px] leading-relaxed">
              {!started && (
                <div className="grid h-full place-items-center text-center text-slate-500">
                  <div>
                    <Workflow className="mx-auto h-8 w-8" />
                    <p className="mt-2">Each tool call, check, retry and decision will appear here.</p>
                  </div>
                </div>
              )}
              <AnimatePresence initial={false}>
                {events.map((e, i) => {
                  const k = KIND_STYLE[e.kind] ?? KIND_STYLE.info;
                  const I = k.icon;
                  return (
                    <motion.div key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} className="flex gap-2 py-0.5">
                      <span className="w-12 shrink-0 text-slate-600">{e.t?.toFixed(2)}s</span>
                      <I className={`mt-1 h-3.5 w-3.5 shrink-0 ${k.color}`} />
                      <span className="shrink-0 text-brand-300">{(e.agent ?? "").replace(" Agent", "")}</span>
                      <span className={k.color}>{e.message}</span>
                    </motion.div>
                  );
                })}
              </AnimatePresence>
              {running && <div className="flex items-center gap-2 py-1 text-slate-500"><Loader2 className="h-3.5 w-3.5 animate-spin" /> working…</div>}
            </div>
          </div>

          {error && (
            <div className="flex items-start gap-3 rounded-2xl bg-rose-50 p-4 text-sm text-rose-800 ring-1 ring-rose-200">
              <CircleAlert className="mt-0.5 h-5 w-5 shrink-0" /> <span>{error}. Is the API running at <code>{API_URL}</code>?</span>
            </div>
          )}

          <AnimatePresence mode="wait">
            {result?.status === "needs_confirmation" && !running && <ConfirmForm key="confirm" result={result} onSubmit={confirm} />}
            {result && result.status !== "needs_confirmation" && !running && <ResultCard key="result" result={result} />}
          </AnimatePresence>
        </div>
      </div>
    </>
  );
}

function StageNode({ stage, state, index }: { stage: (typeof STAGES)[number]; state: StageState; index: number }) {
  const Icon = stage.icon;
  const styles: Record<StageState, string> = {
    idle: "bg-white text-slate-400 ring-slate-200",
    active: "bg-brand-600 text-white ring-brand-200",
    done: "bg-emerald-500 text-white ring-emerald-200",
    error: "bg-rose-500 text-white ring-rose-200",
    waiting: "bg-amber-400 text-white ring-amber-200",
  };
  return (
    <div className="relative flex flex-col items-center text-center">
      <motion.div animate={{ scale: state === "active" ? [1, 1.08, 1] : 1 }} transition={{ repeat: state === "active" ? Infinity : 0, duration: 1.2 }}
        className={`relative z-10 grid h-12 w-12 place-items-center rounded-2xl ring-4 transition-colors duration-500 ${styles[state]}`}>
        {state === "active" && <span className="absolute inset-0 animate-pulse-ring rounded-2xl bg-brand-400/60" />}
        {state === "done" ? <Check className="relative h-6 w-6" /> : state === "error" ? <XCircle className="relative h-6 w-6" /> : state === "waiting" ? <MessageCircleQuestion className="relative h-6 w-6" /> : <Icon className="relative h-5 w-5" />}
      </motion.div>
      <p className="mt-2 text-xs font-bold text-ink sm:text-sm">{stage.label}</p>
      <p className="hidden text-[11px] text-ink-3 sm:block">{state === "waiting" ? "Waiting for you" : stage.sub}</p>
      <span className="sr-only">Step {index + 1}: {state}</span>
    </div>
  );
}

function ConfirmForm({ result, onSubmit }: { result: UploadResult; onSubmit: (a: Record<string, string>) => void }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<Record<string, boolean>>({});
  const qs = result.questions ?? [];
  const complete = qs.every((q) => answers[q.field]?.trim());
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="overflow-hidden rounded-[1.25rem] bg-white shadow-xl ring-2 ring-amber-300">
      <div className="flex items-center gap-3 bg-linear-to-r from-amber-50 to-orange-50 px-6 py-4">
        <MessageCircleQuestion className="h-6 w-6 text-amber-600" />
        <div>
          <p className="font-display font-bold text-ink">The agent wants to double-check {qs.length} detail{qs.length === 1 ? "" : "s"}</p>
          <p className="text-sm text-ink-2">Human-in-the-loop: it never stores a value it can&apos;t support.</p>
        </div>
      </div>
      <div className="space-y-5 p-6">
        {qs.map((q) => (
          <div key={q.field} className="rounded-2xl bg-canvas p-4 ring-1 ring-line">
            <p className="font-medium text-ink">{q.question}</p>
            {q.quote && <p className="mt-2 border-l-2 border-amber-300 pl-3 text-sm italic text-ink-3"><RedactedText text={q.quote} /></p>}
            <div className="mt-3 flex flex-wrap gap-2">
              {q.current !== null && q.current !== undefined && (
                <button onClick={() => { setAnswers((a) => ({ ...a, [q.field]: "yes" })); setEditing((e) => ({ ...e, [q.field]: false })); }}
                  className={`rounded-full px-4 py-2 text-sm font-semibold ring-1 transition ${answers[q.field] === "yes" ? "bg-emerald-500 text-white ring-emerald-500" : "bg-white text-ink ring-line hover:ring-emerald-300"}`}>Yes, correct</button>
              )}
              <button onClick={() => { setEditing((e) => ({ ...e, [q.field]: true })); setAnswers((a) => ({ ...a, [q.field]: "" })); }}
                className={`rounded-full px-4 py-2 text-sm font-semibold ring-1 transition ${editing[q.field] ? "bg-ink text-white ring-ink" : "bg-white text-ink ring-line hover:ring-brand-300"}`}>{q.current === null || q.current === undefined ? "Enter value" : "No, it says…"}</button>
              <button onClick={() => { setAnswers((a) => ({ ...a, [q.field]: "not in letter" })); setEditing((e) => ({ ...e, [q.field]: false })); }}
                className={`rounded-full px-4 py-2 text-sm font-semibold ring-1 transition ${answers[q.field] === "not in letter" ? "bg-slate-600 text-white ring-slate-600" : "bg-white text-ink-2 ring-line"}`}>Not in my letter</button>
            </div>
            {editing[q.field] && (
              <input autoFocus value={answers[q.field] ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [q.field]: e.target.value }))}
                placeholder={q.field === "penalty_amount" ? "e.g. 1,50,000" : q.field === "bond_months" ? "e.g. 24 months" : "Type what your letter says"}
                className="mt-3 h-11 w-full rounded-xl bg-white px-4 outline-none ring-1 ring-line focus:ring-2 focus:ring-brand-300" />
            )}
          </div>
        ))}
        <button disabled={!complete} onClick={() => onSubmit(answers)} className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-ink font-semibold text-white transition hover:bg-brand-700 disabled:opacity-40">
          Send answers and resume <ArrowRight className="h-4 w-4" />
        </button>
      </div>
    </motion.div>
  );
}

function ResultCard({ result }: { result: UploadResult }) {
  const ok = result.status === "stored" || result.status === "queued";
  const d = result.decision ? DECISION_STYLE[result.decision] : null;
  const fields = Object.entries(result.extracted ?? {});
  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="card relative overflow-hidden">
      {ok && <Burst />}
      <div className={`flex flex-col gap-4 p-6 sm:flex-row sm:items-center ${ok ? "bg-linear-to-r from-emerald-50 to-teal-50" : "bg-linear-to-r from-rose-50 to-orange-50"}`}>
        <motion.span initial={{ scale: 0, rotate: -30 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 260, damping: 14 }}
          className={`grid h-14 w-14 shrink-0 place-items-center rounded-2xl text-white shadow-lg ${ok ? "bg-emerald-500" : "bg-rose-500"}`}>
          {ok ? <CheckCircle2 className="h-8 w-8" /> : <XCircle className="h-8 w-8" />}
        </motion.span>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-display text-xl font-bold text-ink">{ok ? "Letter processed" : result.status === "escalated" ? "Escalated to a moderator" : "Not processed"}</p>
            {d && <span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${d.tone}`}>{d.label}</span>}
          </div>
          <p className="mt-1 text-ink-2">{result.message}</p>
        </div>
        {result.company_id && ok && result.status === "stored" && (
          <Link href={`/companies/${result.company_id}`} className="inline-flex shrink-0 items-center gap-2 rounded-full bg-ink px-4 py-2.5 text-sm font-semibold text-white">View company <ArrowRight className="h-4 w-4" /></Link>
        )}
      </div>
      {fields.length > 0 && (
        <div className="p-6">
          <div className="mb-4 flex flex-wrap items-center gap-2 text-sm text-ink-3">
            {result.privacy_report && <span className="inline-flex items-center gap-1.5 rounded-full bg-violet-50 px-3 py-1 font-medium text-violet-700"><Eye className="h-4 w-4" /> {result.privacy_report.redactions} redactions · {result.privacy_report.attempts} scan{result.privacy_report.attempts > 1 ? "s" : ""}</span>}
            <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 font-medium text-ink-2"><Trash2 className="h-4 w-4" /> Document deleted</span>
          </div>
          <div className="divide-y divide-line overflow-hidden rounded-2xl ring-1 ring-line">
            {fields.map(([f, v], i) => (
              <motion.div key={f} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.04 }} className="grid gap-2 bg-white px-4 py-3 sm:grid-cols-[170px_1fr_110px] sm:items-center">
                <span className="text-xs font-semibold uppercase tracking-wide text-ink-3">{FIELD_LABELS[f] ?? f}</span>
                <span className="min-w-0">
                  <span className="block text-sm font-semibold text-ink">{fieldValue(f, v.value)}</span>
                  {v.quote && <span className="mt-0.5 block truncate text-xs text-ink-3" title={v.quote}>“<RedactedText text={v.quote} />”</span>}
                  {v.source?.startsWith("uploader") && <span className="mt-1 inline-block rounded bg-amber-50 px-1.5 text-[10px] font-semibold uppercase text-amber-700">from you</span>}
                  {v.source === "reread" && <span className="mt-1 inline-block rounded bg-sky-50 px-1.5 text-[10px] font-semibold uppercase text-sky-700">self-corrected</span>}
                </span>
                <span className="flex items-center gap-2">
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <motion.span initial={{ width: 0 }} animate={{ width: `${Math.round((v.confidence ?? 0) * 100)}%` }} transition={{ duration: 0.8, delay: i * 0.04 }} className="block h-full rounded-full" style={{ background: "var(--series-1)" }} />
                  </span>
                  <span className="w-9 text-right text-xs font-medium text-ink-3">{Math.round((v.confidence ?? 0) * 100)}%</span>
                </span>
              </motion.div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}

function Burst() {
  const pieces = Array.from({ length: 18 });
  return (
    <div className="pointer-events-none absolute left-12 top-12 z-10">
      {pieces.map((_, i) => {
        const angle = (i / pieces.length) * Math.PI * 2;
        const dist = 60 + (i % 3) * 25;
        const colors = ["#6366f1", "#10b981", "#f59e0b", "#ec4899", "#0ea5e9"];
        return (
          <motion.span key={i} className="absolute h-2 w-2 rounded-sm" style={{ background: colors[i % colors.length] }}
            initial={{ x: 0, y: 0, opacity: 1, rotate: 0 }} animate={{ x: Math.cos(angle) * dist, y: Math.sin(angle) * dist, opacity: 0, rotate: 180 }} transition={{ duration: 1.1, ease: "easeOut" }} />
        );
      })}
    </div>
  );
}
