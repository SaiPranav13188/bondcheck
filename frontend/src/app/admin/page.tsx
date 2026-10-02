"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Activity, BellRing, Check, ChevronRight, GitCompareArrows, GitMerge, Inbox, KeyRound, Loader2, LogOut, Radar, Repeat, ShieldCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import RedactedText from "@/components/RedactedText";
import { Monogram, useApi } from "@/components/ui";
import { getJSON, postJSON, type Conflict, type OfferRecord } from "@/lib/api";
import { DECISION_STYLE, FIELD_LABELS, fieldValue, inr, shortName } from "@/lib/format";

type QueueItem = { id: number; record_id: number | null; reason: string; note: string; status: string; created_at: string; record?: OfferRecord & { company_name: string }; similar?: { id: number; name: string; score: number }[] };
type RunRow = { run_ref: string; workflow: string; started: string; tokens: number; ms: number; agents: number; status: string; agent_list: { agent: string; status: string }[] };
type RunDetail = { id: number; agent: string; status: string; duration_ms: number; tokens_used: number; steps: { kind: string; message: string; t: number }[] };
type Overview = { agents: { agent: string; runs: number; avg_ms: number; tokens: number; ok: number; not_ok: number }[]; workflows: { workflow: string; runs: number }[]; self_corrections: number; queue_pending: number; open_conflicts: number; health: { mode: string; database: string; ocr: string } };

const TABS = [
  { key: "overview", label: "Overview", icon: Activity },
  { key: "queue", label: "Moderation queue", icon: Inbox },
  { key: "conflicts", label: "Conflicts", icon: GitCompareArrows },
  { key: "runs", label: "Agent runs", icon: Repeat },
] as const;

export default function AdminPage() {
  const [token, setToken] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("overview");
  const [authError, setAuthError] = useState("");

  useEffect(() => {
    // Browser storage only exists after mount; reading it here is the intended one-time sync.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    try { setToken(localStorage.getItem("bondcheck-admin")); } catch {}
  }, []);

  const login = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await getJSON("/admin/overview", { headers: { "x-admin-token": input } });
      try { localStorage.setItem("bondcheck-admin", input); } catch {}
      setToken(input);
      setAuthError("");
    } catch {
      setAuthError("That token wasn't accepted.");
    }
  };

  if (!token) {
    return (
      <div className="container-x grid min-h-[70vh] place-items-center py-16">
        <motion.form onSubmit={login} initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="card w-full max-w-md p-8">
          <span className="grid h-12 w-12 place-items-center rounded-2xl bg-ink text-white"><KeyRound className="h-6 w-6" /></span>
          <h1 className="mt-5 font-display text-2xl font-bold text-ink">Moderator console</h1>
          <p className="mt-1 text-sm text-ink-3">Review outliers, new companies and conflicts, and inspect every agent step. Local default token: <code className="rounded bg-canvas px-1">dev-admin-token</code></p>
          <input type="password" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Admin token" className="mt-6 h-12 w-full rounded-xl bg-canvas px-4 outline-none ring-1 ring-line focus:ring-2 focus:ring-brand-300" />
          {authError && <p className="mt-2 text-sm text-rose-600">{authError}</p>}
          <button className="mt-4 h-12 w-full rounded-xl bg-ink font-semibold text-white transition hover:bg-brand-700">Sign in</button>
        </motion.form>
      </div>
    );
  }

  const headers = { "x-admin-token": token };
  return (
    <div className="container-x py-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-brand-600">Human in the loop</p>
          <h1 className="font-display text-3xl font-extrabold text-ink">Moderator console</h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <CronButton path="/cron/monitor" label="Run Monitor Agent" icon={Radar} headers={headers} />
          <CronButton path="/cron/alerts" label="Run Alert Agent" icon={BellRing} headers={headers} />
          <button onClick={() => { try { localStorage.removeItem("bondcheck-admin"); } catch {} setToken(null); }} className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium text-ink-3 ring-1 ring-line hover:text-ink"><LogOut className="h-4 w-4" /> Sign out</button>
        </div>
      </div>
      <div className="mt-6 flex gap-1 overflow-x-auto rounded-2xl bg-white p-1.5 ring-1 ring-line">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)} className={`relative inline-flex shrink-0 items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition ${tab === t.key ? "text-white" : "text-ink-3 hover:text-ink"}`}>
            {tab === t.key && <motion.span layoutId="admin-tab" className="absolute inset-0 rounded-xl bg-ink" />}
            <t.icon className="relative h-4 w-4" /><span className="relative">{t.label}</span>
          </button>
        ))}
      </div>
      <div className="mt-6">
        {tab === "overview" && <OverviewTab headers={headers} />}
        {tab === "queue" && <QueueTab headers={headers} />}
        {tab === "conflicts" && <ConflictsTab headers={headers} />}
        {tab === "runs" && <RunsTab headers={headers} />}
      </div>
    </div>
  );
}

function useAdmin<T>(path: string, headers: Record<string, string>) {
  const key = headers["x-admin-token"];
  return useApi(() => getJSON<T>(path, { headers: { "x-admin-token": key } }), [path, key]);
}

function CronButton({ path, label, icon: Icon, headers }: { path: string; label: string; icon: typeof Radar; headers: Record<string, string> }) {
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  const [summary, setSummary] = useState("");
  const run = async () => {
    setState("busy");
    try {
      const r = await postJSON<{ result: Record<string, unknown> }>(path, {}, headers);
      const res = r.result;
      setSummary("sent" in res ? `${res.sent} sent, ${res.skipped} skipped` : `${(res.gaps as unknown[]).length} gaps, ${res.requests} new requests`);
      setState("done");
    } catch {
      setSummary("failed");
      setState("done");
    }
  };
  return (
    <button onClick={run} disabled={state === "busy"} className="inline-flex items-center gap-2 rounded-full bg-white px-4 py-2 text-sm font-semibold text-ink ring-1 ring-line transition hover:ring-brand-300">
      {state === "busy" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Icon className="h-4 w-4 text-brand-600" />} {label}
      {state === "done" && <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-xs text-emerald-700">{summary}</span>}
    </button>
  );
}

function OverviewTab({ headers }: { headers: Record<string, string> }) {
  const { data } = useAdmin<Overview>("/admin/overview", headers);
  if (!data) return <Loader2 className="h-6 w-6 animate-spin text-ink-3" />;
  const max = Math.max(...data.agents.map((a) => a.runs), 1);
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {[
          ["Pending reviews", data.queue_pending, Inbox, "text-violet-600 bg-violet-50"],
          ["Open conflicts", data.open_conflicts, GitCompareArrows, "text-amber-600 bg-amber-50"],
          ["Self-corrections", data.self_corrections, Repeat, "text-sky-600 bg-sky-50"],
          ["Engine", data.health.mode, ShieldCheck, "text-emerald-600 bg-emerald-50"],
        ].map(([l, v, I, tone]) => {
          const Icon = I as typeof Inbox;
          return (
            <div key={l as string} className="card p-5">
              <span className={`grid h-10 w-10 place-items-center rounded-xl ${tone}`}><Icon className="h-5 w-5" /></span>
              <p className="mt-3 font-display text-2xl font-bold text-ink">{String(v)}</p>
              <p className="text-sm text-ink-3">{l as string}</p>
            </div>
          );
        })}
      </div>
      <div className="card overflow-hidden">
        <p className="px-6 pt-6 font-display text-lg font-bold text-ink">Agents (from agent_runs)</p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead><tr className="border-y border-line bg-canvas text-left text-xs uppercase tracking-wide text-ink-3"><th className="px-6 py-3">Agent</th><th className="px-3 py-3">Runs</th><th className="px-3 py-3">Avg time</th><th className="px-3 py-3">Tokens</th><th className="px-6 py-3 text-right">Success</th></tr></thead>
            <tbody>
              {data.agents.map((a) => (
                <tr key={a.agent} className="border-b border-line last:border-0">
                  <td className="px-6 py-3 font-medium text-ink">{a.agent}</td>
                  <td className="px-3 py-3"><div className="flex items-center gap-2"><div className="h-2 w-24 rounded-full bg-slate-100"><div className="h-full rounded-full" style={{ width: `${(a.runs / max) * 100}%`, background: "var(--series-1)" }} /></div><span className="text-ink-2">{a.runs}</span></div></td>
                  <td className="px-3 py-3 text-ink-2">{Math.round(a.avg_ms)} ms</td>
                  <td className="px-3 py-3 text-ink-2">{(a.tokens ?? 0).toLocaleString("en-IN")}</td>
                  <td className="px-6 py-3 text-right text-ink-2">{Math.round((a.ok / Math.max(a.runs, 1)) * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <p className="text-xs text-ink-3">Database: {data.health.database} · OCR: {data.health.ocr}</p>
    </div>
  );
}

function QueueTab({ headers }: { headers: Record<string, string> }) {
  const { data, loading, reload } = useAdmin<QueueItem[]>("/admin/queue", headers);
  const [busy, setBusy] = useState<number | null>(null);
  const act = async (id: number, action: string, merge_into?: number) => {
    setBusy(id);
    try { await postJSON(`/admin/queue/${id}`, { action, merge_into }, headers); } finally { setBusy(null); reload(); }
  };
  if (loading && !data) return <Loader2 className="h-6 w-6 animate-spin text-ink-3" />;
  if (!data?.length) return <Empty text="The queue is empty. Nice." />;
  return (
    <div className="space-y-4">
      <AnimatePresence>
        {data.map((it) => {
          const d = DECISION_STYLE[it.reason] ?? { label: it.reason, tone: "bg-slate-100 text-ink-2 ring-slate-200" };
          const r = it.record;
          return (
            <motion.div key={it.id} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: 40 }} className="card overflow-hidden">
              <div className="flex flex-wrap items-center gap-3 border-b border-line p-5">
                {r && <Monogram id={r.company_id} name={r.company_name} size="sm" />}
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-ink">{r ? shortName(r.company_name) : "Escalated run"} {r && <span className="font-normal text-ink-3">· record #{r.id} · {r.batch_year}</span>}</p>
                  <p className="text-sm text-ink-3">{it.note}</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${d.tone}`}>{d.label}</span>
              </div>
              {r && (
                <div className="grid gap-5 p-5 lg:grid-cols-[1fr_260px]">
                  <div className="space-y-2">
                    <div className="flex flex-wrap gap-2 text-sm">
                      {["bond_months", "penalty_amount", "ctc_annual", "penalty_prorated"].map((f) => (
                        <span key={f} className="rounded-lg bg-canvas px-2.5 py-1 text-ink-2"><span className="text-ink-3">{FIELD_LABELS[f]}:</span> {fieldValue(f, (r as unknown as Record<string, unknown>)[f])}</span>
                      ))}
                    </div>
                    {r.evidence.slice(0, 4).map((e, i) => (
                      <p key={i} className="rounded-xl bg-canvas p-3 text-sm text-ink-2"><span className="mr-1 text-[11px] font-semibold uppercase text-brand-700">{FIELD_LABELS[e.field] ?? e.field}</span> “<RedactedText text={e.quote} />”</p>
                    ))}
                  </div>
                  <div className="space-y-2">
                    <button disabled={busy === it.id} onClick={() => act(it.id, "approve")} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 py-2.5 text-sm font-semibold text-white hover:bg-emerald-700"><Check className="h-4 w-4" /> Approve</button>
                    <button disabled={busy === it.id} onClick={() => act(it.id, "reject")} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white py-2.5 text-sm font-semibold text-rose-700 ring-1 ring-rose-200 hover:bg-rose-50"><X className="h-4 w-4" /> Reject</button>
                    {it.reason === "new_company" && it.similar?.filter((s) => s.id !== r.company_id && s.score >= 60).map((s) => (
                      <button key={s.id} disabled={busy === it.id} onClick={() => act(it.id, "merge", s.id)} className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-white py-2.5 text-sm font-semibold text-ink ring-1 ring-line hover:ring-brand-300"><GitMerge className="h-4 w-4" /> Merge into {shortName(s.name)} ({s.score})</button>
                    ))}
                  </div>
                </div>
              )}
              {!r && (
                <div className="flex justify-end p-4"><button onClick={() => act(it.id, "dismiss")} className="rounded-xl bg-ink px-4 py-2 text-sm font-semibold text-white">Dismiss</button></div>
              )}
            </motion.div>
          );
        })}
      </AnimatePresence>
    </div>
  );
}

function ConflictsTab({ headers }: { headers: Record<string, string> }) {
  const { data, reload } = useAdmin<Conflict[]>("/admin/conflicts", headers);
  const resolve = async (id: number, keep?: string) => {
    await postJSON(`/admin/conflicts/${id}/resolve`, { keep_value: keep ?? null }, headers);
    reload();
  };
  if (!data) return <Loader2 className="h-6 w-6 animate-spin text-ink-3" />;
  if (!data.length) return <Empty text="No conflicts recorded." />;
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {data.map((c) => (
        <div key={c.id} className={`card p-5 ${c.status === "resolved" ? "opacity-60" : ""}`}>
          <div className="flex items-center justify-between">
            <p className="font-semibold text-ink">{shortName(c.name ?? "")}</p>
            <span className={`rounded-full px-2.5 py-1 text-xs font-semibold ${c.status === "open" ? "bg-amber-50 text-amber-800" : "bg-slate-100 text-ink-3"}`}>{c.status}</span>
          </div>
          <p className="text-sm text-ink-3">{FIELD_LABELS[c.field]} · {c.batch_year} · {c.role}</p>
          <div className="mt-4 space-y-2">
            {Object.entries(c.values_seen).sort((a, b) => b[1] - a[1]).map(([v, n]) => (
              <div key={v} className="flex items-center justify-between rounded-xl bg-canvas px-3 py-2 text-sm">
                <span className="font-semibold text-ink">{c.field === "penalty_amount" ? inr(Number(v)) : v} <span className="font-normal text-ink-3">· {n} letters</span></span>
                {c.status === "open" && <button onClick={() => resolve(c.id, v)} className="rounded-lg bg-white px-2.5 py-1 text-xs font-semibold text-ink ring-1 ring-line hover:ring-brand-300">Keep this</button>}
              </div>
            ))}
          </div>
          {c.status === "open" && <button onClick={() => resolve(c.id)} className="mt-3 text-sm font-semibold text-brand-700">Mark resolved, keep all</button>}
        </div>
      ))}
    </div>
  );
}

function RunsTab({ headers }: { headers: Record<string, string> }) {
  const { data } = useAdmin<RunRow[]>("/admin/runs?limit=60", headers);
  const [open, setOpen] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<{ ref: string; rows: RunDetail[] } | null>(null);
  const token = headers["x-admin-token"];
  useEffect(() => {
    if (!open) return;
    getJSON<RunDetail[]>(`/admin/runs/${open}`, { headers: { "x-admin-token": token } })
      .then((rows) => setLoaded({ ref: open, rows }))
      .catch(() => setLoaded({ ref: open, rows: [] }));
  }, [open, token]);
  const detail = loaded?.ref === open ? loaded.rows : null;
  if (!data) return <Loader2 className="h-6 w-6 animate-spin text-ink-3" />;
  const tone: Record<string, string> = { success: "bg-emerald-50 text-emerald-700", escalated: "bg-amber-50 text-amber-800", failed: "bg-rose-50 text-rose-700", paused: "bg-sky-50 text-sky-700" };
  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
      <div className="card max-h-[70vh] overflow-y-auto p-2">
        {data.map((r) => (
          <button key={r.run_ref} onClick={() => setOpen(r.run_ref)} className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition ${open === r.run_ref ? "bg-brand-50" : "hover:bg-canvas"}`}>
            <span className="font-mono text-xs text-ink-3">{r.run_ref.slice(0, 8)}</span>
            <span className="flex-1 text-sm font-medium capitalize text-ink">{r.workflow}</span>
            <span className="text-xs text-ink-3">{r.agents} agent{r.agents === 1 ? "" : "s"} · {r.ms} ms</span>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${tone[r.status]}`}>{r.status}</span>
            <ChevronRight className="h-4 w-4 text-ink-3" />
          </button>
        ))}
      </div>
      <div className="card p-6">
        {!open && <p className="text-ink-3">Select a run to see every tool call, check, retry and decision.</p>}
        {open && !detail && <Loader2 className="h-6 w-6 animate-spin text-ink-3" />}
        {detail?.map((a) => (
          <div key={a.id} className="mb-5 last:mb-0">
            <p className="flex items-center gap-2 font-semibold text-ink">{a.agent} <span className={`rounded-full px-2 py-0.5 text-[11px] ${tone[a.status] ?? "bg-slate-100"}`}>{a.status}</span> <span className="text-xs font-normal text-ink-3">{a.duration_ms} ms · {a.tokens_used} tokens</span></p>
            <ul className="mt-2 space-y-1 border-l-2 border-brand-100 pl-4">
              {(a.steps ?? []).map((s, i) => (
                <li key={i} className="text-sm text-ink-2"><span className="mr-2 font-mono text-[11px] uppercase text-brand-600">{s.kind}</span>{s.message}</li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="card p-12 text-center text-ink-3"><ShieldCheck className="mx-auto h-10 w-10 text-emerald-400" /><p className="mt-3">{text}</p></div>;
}
