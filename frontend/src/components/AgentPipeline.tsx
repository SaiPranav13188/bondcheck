"use client";

import { motion } from "framer-motion";
import { BellRing, Bot, Eye, FileSearch, MessageSquareText, Radar, ShieldCheck, Workflow } from "lucide-react";
import { useState } from "react";

export const AGENTS = [
  { key: "orchestrator", name: "Orchestrator", icon: Workflow, color: "from-slate-700 to-slate-900", role: "Plans and routes every event, retries failures (max 2), enforces a token budget and escalates to humans.", tools: ["classify_document", "route", "retry", "escalate"] },
  { key: "privacy", name: "Privacy Agent", icon: Eye, color: "from-indigo-500 to-violet-600", role: "Detects and redacts names, phones, PAN, Aadhaar, addresses, then re-scans. Rejects the upload after 3 failed attempts.", tools: ["detect_pii", "redact", "scan_for_remaining_pii"] },
  { key: "extraction", name: "Extraction Agent", icon: FileSearch, color: "from-sky-500 to-blue-600", role: "Extracts 12 fields, each with a quote. Verifies every quote exists, re-reads sections that fail, and asks you when unsure.", tools: ["read_section", "verify_quote", "normalize_amount", "ask_uploader"] },
  { key: "verification", name: "Verification Agent", icon: ShieldCheck, color: "from-emerald-500 to-teal-600", role: "Decides: corroborate, new variant, conflict, outlier, or new company, and keeps the company summary trustworthy.", tools: ["find_company", "run_readonly_sql", "compare_records"] },
  { key: "qa", name: "Q&A Agent", icon: MessageSquareText, color: "from-fuchsia-500 to-pink-600", role: "Answers with read-only SQL and a deterministic calculator, citing record IDs, upload counts and dates.", tools: ["run_readonly_sql", "calc_exit_cost", "get_evidence"] },
  { key: "monitor", name: "Monitor Agent", icon: Radar, color: "from-amber-500 to-orange-600", role: "Daily: finds drives in the next 30 days with missing, stale or conflicting data and asks seniors to upload.", tools: ["get_upcoming_drives", "web_search", "save_public_source"] },
  { key: "alert", name: "Alert Agent", icon: BellRing, color: "from-rose-500 to-red-600", role: "7 days before a drive, emails subscribed students a summary, and decides whether an alert is worth sending.", tools: ["get_subscriptions", "get_company_summary", "send_email"] },
];

export default function AgentPipeline({ dark = false }: { dark?: boolean }) {
  const [active, setActive] = useState(2);
  const a = AGENTS[active];
  return (
    <div className="grid items-center gap-10 lg:grid-cols-[1.2fr_1fr]">
      <div className="relative">
        <div className="relative grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
          {AGENTS.map((ag, i) => {
            const Icon = ag.icon;
            const on = i === active;
            return (
              <motion.button
                key={ag.key}
                onMouseEnter={() => setActive(i)}
                onClick={() => setActive(i)}
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.08 }}
                className={`relative flex flex-col items-start gap-3 rounded-2xl p-4 text-left transition duration-300 ${i === 0 ? "col-span-2 sm:col-span-3 sm:mx-auto sm:w-1/2" : ""} ${on ? (dark ? "bg-white/15 ring-2 ring-brand-300" : "bg-white shadow-xl ring-2 ring-brand-400") : dark ? "bg-white/5 ring-1 ring-white/10 hover:bg-white/10" : "bg-white/70 ring-1 ring-slate-200 hover:bg-white"}`}
              >
                <span className={`relative grid h-11 w-11 place-items-center rounded-xl bg-linear-to-br text-white shadow-lg ${ag.color}`}>
                  {on && <span className="absolute inset-0 animate-pulse-ring rounded-xl bg-brand-400/50" />}
                  <Icon className="relative h-5 w-5" />
                </span>
                <span className={`font-display text-sm font-bold ${dark ? "text-white" : "text-ink"}`}>{ag.name}</span>
              </motion.button>
            );
          })}
        </div>
      </div>

      <motion.div key={a.key} initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.35 }}
        className={`rounded-3xl p-7 ${dark ? "bg-white/5 ring-1 ring-white/10" : "card"}`}>
        <div className="flex items-center gap-3">
          <span className={`grid h-12 w-12 place-items-center rounded-2xl bg-linear-to-br text-white shadow-lg ${a.color}`}><a.icon className="h-6 w-6" /></span>
          <div>
            <p className={`text-xs font-semibold uppercase tracking-widest ${dark ? "text-brand-300" : "text-brand-600"}`}>Agent {active + 1} of 7</p>
            <p className={`font-display text-xl font-bold ${dark ? "text-white" : "text-ink"}`}>{a.name}</p>
          </div>
        </div>
        <p className={`mt-4 leading-relaxed ${dark ? "text-slate-300" : "text-ink-2"}`}>{a.role}</p>
        <p className={`mt-5 text-xs font-semibold uppercase tracking-wide ${dark ? "text-slate-400" : "text-ink-3"}`}>Tools it calls</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {a.tools.map((t) => (
            <span key={t} className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 font-mono text-xs ${dark ? "bg-white/10 text-brand-100" : "bg-slate-100 text-ink-2"}`}>
              <Bot className="h-3 w-3" /> {t}()
            </span>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
