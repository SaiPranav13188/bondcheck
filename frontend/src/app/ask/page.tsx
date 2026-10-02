"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, Bot, Calculator, Database, FileSearch, Loader2, Quote, Scale, Search, Sparkles, User, X } from "lucide-react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import RedactedText from "@/components/RedactedText";
import { getJSON, streamEvents, type AgentEvent, type OfferRecord } from "@/lib/api";
import { dateShort, FIELD_LABELS, fieldValue, shortName } from "@/lib/format";

type Citation = { record_id: number; batch_year: number; role: string | null; created_at: string };
type Msg = { role: "user" | "assistant"; content: string; steps?: AgentEvent[]; citations?: Citation[]; pending?: boolean };

const SUGGESTIONS = [
  "If I join Nexora and leave after 10 months, what could I owe?",
  "What is the bond at Rivanta Infotech?",
  "Which companies have no bond?",
  "Which companies have the highest penalties?",
  "Does Brightloom keep original certificates?",
  "Is the Quantiva penalty pro-rated?",
];

const TOOL_ICON: Record<string, typeof Database> = { find_company: Search, run_readonly_sql: Database, calc_exit_cost: Calculator, get_evidence: FileSearch };

export default function AskPage() {
  return <Suspense><Ask /></Suspense>;
}

function Ask() {
  const params = useSearchParams();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [record, setRecord] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const asked = useRef(false);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs]);
  useEffect(() => {
    const q = params.get("q");
    if (q && !asked.current) { asked.current = true; send(q); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    const history = msgs.filter((m) => !m.pending).map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "", steps: [], pending: true }]);
    const update = (fn: (m: Msg) => Msg) => setMsgs((all) => all.map((m, i) => (i === all.length - 1 ? fn(m) : m)));
    try {
      await streamEvents("/ask", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ question: q, history }) }, (ev) => {
        if (ev.kind === "result") update((m) => ({ ...m, content: ev.result.answer, citations: ev.result.citations, pending: false }));
        else if (ev.kind === "tool") update((m) => ({ ...m, steps: [...(m.steps ?? []), ev] }));
      });
    } catch (e) {
      update((m) => ({ ...m, content: `Sorry, I couldn't reach the BondCheck API (${(e as Error).message}).`, pending: false }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="container-x grid gap-8 py-8 lg:grid-cols-[1fr_340px]">
      <div className="card flex min-h-[calc(100vh-9rem)] flex-col overflow-hidden">
        {/* header */}
        <div className="flex items-center gap-3 border-b border-line px-5 py-4">
          <span className="relative grid h-10 w-10 place-items-center rounded-xl bg-linear-to-br from-fuchsia-500 to-pink-600 text-white shadow-lg"><Bot className="h-5 w-5" /><span className="absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-white bg-emerald-400" /></span>
          <div>
            <p className="font-display font-bold text-ink">BondCheck Q&amp;A Agent</p>
            <p className="text-xs text-ink-3">Answers only from verified uploads · cites every claim</p>
          </div>
          {msgs.length > 0 && <button onClick={() => setMsgs([])} className="ml-auto rounded-full px-3 py-1.5 text-xs font-semibold text-ink-3 ring-1 ring-line hover:text-ink">New chat</button>}
        </div>

        {/* messages */}
        <div className="flex-1 space-y-6 overflow-y-auto px-4 py-6 sm:px-6">
          {msgs.length === 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mx-auto max-w-xl pt-6 text-center">
              <div className="relative mx-auto h-40 w-40 overflow-hidden rounded-full ring-8 ring-brand-50">
                <Image src="/images/study-group.jpg" alt="" fill sizes="160px" className="object-cover" />
              </div>
              <h1 className="mt-6 font-display text-3xl font-extrabold text-ink">Ask before you sign</h1>
              <p className="mt-2 text-ink-2">Bond length, penalties, pro-rating, what leaving early would cost. Every answer cites the letters it came from.</p>
              <div className="mt-8 grid gap-2 sm:grid-cols-2">
                {SUGGESTIONS.map((s, i) => (
                  <motion.button key={s} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.05 }} onClick={() => send(s)}
                    className="rounded-2xl bg-canvas px-4 py-3 text-left text-sm text-ink-2 ring-1 ring-line transition hover:bg-white hover:text-ink hover:ring-brand-300">
                    <Sparkles className="mb-1 h-4 w-4 text-brand-500" /> {s}
                  </motion.button>
                ))}
              </div>
            </motion.div>
          )}
          <AnimatePresence initial={false}>
            {msgs.map((m, i) => (
              <motion.div key={i} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className={`flex gap-3 ${m.role === "user" ? "flex-row-reverse" : ""}`}>
                <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${m.role === "user" ? "bg-ink text-white" : "bg-linear-to-br from-fuchsia-500 to-pink-600 text-white"}`}>
                  {m.role === "user" ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
                </span>
                <div className={`max-w-[85%] ${m.role === "user" ? "items-end" : ""}`}>
                  {m.role === "assistant" && (m.steps?.length ?? 0) > 0 && (
                    <div className="mb-2 flex flex-wrap gap-1.5">
                      {m.steps!.map((s, j) => {
                        const tool = (s.message ?? "").split("(")[0].split(" ")[0];
                        const I = TOOL_ICON[tool] ?? Database;
                        return (
                          <motion.span key={j} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} title={s.message}
                            className="inline-flex max-w-[260px] items-center gap-1.5 truncate rounded-lg bg-slate-100 px-2 py-1 font-mono text-[11px] text-ink-2">
                            <I className="h-3 w-3 shrink-0 text-brand-600" /> <span className="truncate">{s.message}</span>
                          </motion.span>
                        );
                      })}
                    </div>
                  )}
                  <div className={`rounded-2xl px-4 py-3 leading-relaxed ${m.role === "user" ? "rounded-tr-md bg-ink text-white" : "rounded-tl-md bg-canvas text-ink ring-1 ring-line"}`}>
                    {m.pending ? (
                      <span className="flex items-center gap-2 text-sm text-ink-3"><Loader2 className="h-4 w-4 animate-spin" /> Searching verified records…</span>
                    ) : (
                      <AnswerText text={m.content} onCite={setRecord} />
                    )}
                  </div>
                  {(m.citations?.length ?? 0) > 0 && (
                    <div className="mt-2 flex flex-wrap items-center gap-1.5">
                      <span className="text-xs text-ink-3">Sources:</span>
                      {m.citations!.map((c) => (
                        <button key={c.record_id} onClick={() => setRecord(c.record_id)} className="inline-flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-xs font-medium text-brand-700 ring-1 ring-brand-200 transition hover:bg-brand-50">
                          <Quote className="h-3 w-3" /> #{c.record_id} · {c.batch_year}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
          <div ref={endRef} />
        </div>

        {/* input */}
        <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="border-t border-line p-3 sm:p-4">
          <div className="flex items-end gap-2 rounded-2xl bg-canvas p-2 ring-1 ring-line focus-within:ring-2 focus-within:ring-brand-300">
            <textarea value={input} onChange={(e) => setInput(e.target.value)} rows={1}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
              placeholder="e.g. What happens if I leave Brightloom after 1 year?" className="max-h-40 min-h-[44px] flex-1 resize-none bg-transparent px-3 py-2.5 outline-none placeholder:text-slate-400" aria-label="Your question" />
            <button disabled={busy || !input.trim()} className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-ink text-white transition hover:bg-brand-700 disabled:opacity-30" aria-label="Send">
              {busy ? <Loader2 className="h-5 w-5 animate-spin" /> : <ArrowUp className="h-5 w-5" />}
            </button>
          </div>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-center text-xs text-ink-3"><Scale className="h-3.5 w-3.5" /> Information from uploaded letters, not legal advice.</p>
        </form>
      </div>

      {/* side panel */}
      <aside className="hidden space-y-6 lg:block">
        <div className="relative h-56 overflow-hidden rounded-[1.25rem]">
          <Image src="/images/students-laptop.jpg" alt="Students discussing" fill sizes="340px" className="object-cover" />
          <div className="absolute inset-0 bg-linear-to-t from-ink/90 to-transparent" />
          <p className="absolute bottom-4 left-5 right-5 font-display text-lg font-bold text-white">Answers your seniors would give, with receipts.</p>
        </div>
        <div className="card space-y-4 p-5">
          <p className="font-display font-bold text-ink">How the agent answers</p>
          {[
            [Search, "find_company", "Matches name variants like “Nexora Tech Pvt Ltd”"],
            [Database, "run_readonly_sql", "Read-only role, SELECT only, automatic LIMIT"],
            [Calculator, "calc_exit_cost", "Python does the maths, never the model"],
            [FileSearch, "get_evidence", "Pulls the exact redacted clause"],
          ].map(([I, t, d]) => {
            const Icon = I as typeof Search;
            return (
              <div key={t as string} className="flex gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-brand-50 text-brand-600"><Icon className="h-4 w-4" /></span>
                <div><p className="font-mono text-xs font-semibold text-ink">{t as string}()</p><p className="text-sm text-ink-3">{d as string}</p></div>
              </div>
            );
          })}
        </div>
      </aside>

      <RecordModal id={record} onClose={() => setRecord(null)} />
    </div>
  );
}

// Renders markdown bold and italics, and turns "#12" into clickable citations.
function AnswerText({ text, onCite }: { text: string; onCite: (id: number) => void }) {
  return (
    <div className="space-y-2 text-[15px]">
      {text.split(/\n{2,}/).map((para, i) => (
        <p key={i} className={para.startsWith("*(") ? "text-xs text-ink-3" : ""}>
          {para.split(/(#\d+|\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, j) => {
            if (/^#\d+$/.test(part)) return <button key={j} onClick={() => onCite(Number(part.slice(1)))} className="rounded bg-brand-100 px-1 font-mono text-[13px] font-semibold text-brand-700 hover:bg-brand-200">{part}</button>;
            if (part.startsWith("**")) return <strong key={j}>{part.slice(2, -2)}</strong>;
            if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={j}>{part.slice(1, -1)}</em>;
            return <span key={j}>{part}</span>;
          })}
        </p>
      ))}
    </div>
  );
}

function RecordModal({ id, onClose }: { id: number | null; onClose: () => void }) {
  const [loaded, setLoaded] = useState<{ id: number; rec: OfferRecord | null; err: boolean } | null>(null);
  useEffect(() => {
    if (!id) return;
    getJSON<OfferRecord>(`/record/${id}`).then((rec) => setLoaded({ id, rec, err: false })).catch(() => setLoaded({ id, rec: null, err: true }));
  }, [id]);
  const rec = loaded?.id === id ? loaded.rec : null;
  const err = loaded?.id === id ? loaded.err : false;
  return (
    <AnimatePresence>
      {id && (
        <motion.div className="fixed inset-0 z-[60] grid place-items-center bg-ink/50 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div className="relative max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white p-6 shadow-2xl" initial={{ scale: 0.94, y: 16 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.96, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
            <button onClick={onClose} className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-full text-ink-3 hover:bg-canvas" aria-label="Close"><X className="h-5 w-5" /></button>
            <p className="font-mono text-xs font-semibold text-brand-600">Record #{id}</p>
            {err && <p className="mt-4 text-ink-3">This record isn&apos;t available.</p>}
            {!rec && !err && <Loader2 className="mt-6 h-6 w-6 animate-spin text-ink-3" />}
            {rec && (
              <>
                <p className="mt-1 font-display text-xl font-bold text-ink">{shortName(rec.company_name ?? "")}</p>
                <p className="text-sm text-ink-3">{rec.batch_year} batch · {rec.role ?? "role not stated"} · uploaded {dateShort(rec.created_at)}</p>
                <div className="mt-5 space-y-2.5">
                  {rec.evidence.map((e, i) => (
                    <div key={i} className="rounded-xl bg-canvas p-3 ring-1 ring-line">
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-brand-700">{FIELD_LABELS[e.field] ?? e.field}: {e.field === "company_name" ? shortName(rec.company_name ?? "") : fieldValue(e.field, (rec as unknown as Record<string, unknown>)[e.field])}</p>
                      <p className="mt-1 text-sm text-ink-2">“<RedactedText text={e.quote} />”</p>
                    </div>
                  ))}
                </div>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
