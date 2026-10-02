"use client";

import { AnimatePresence, motion } from "framer-motion";
import { BellRing, CheckCircle2, X } from "lucide-react";
import { useState } from "react";
import { postJSON } from "@/lib/api";

export default function SubscribeModal({ open, onClose, companyId, companyName }: { open: boolean; onClose: () => void; companyId: number; companyName: string }) {
  const [email, setEmail] = useState("");
  const [all, setAll] = useState(false);
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");
  const [msg, setMsg] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState("saving");
    try {
      await postJSON("/subscribe", { email, company_ids: [companyId], alert_all: all });
      setState("done");
    } catch (err) {
      setMsg((err as Error).message.includes("email") ? "Please enter a valid email." : "Couldn't subscribe right now.");
      setState("error");
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-[60] grid place-items-center bg-ink/50 p-4 backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}>
          <motion.div role="dialog" aria-modal className="relative w-full max-w-md overflow-hidden rounded-3xl bg-white p-7 shadow-2xl" initial={{ scale: 0.92, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, opacity: 0 }} onClick={(e) => e.stopPropagation()}>
            <button onClick={onClose} className="absolute right-4 top-4 grid h-9 w-9 place-items-center rounded-full text-ink-3 hover:bg-canvas" aria-label="Close"><X className="h-5 w-5" /></button>
            {state === "done" ? (
              <div className="py-6 text-center">
                <motion.div initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 260, damping: 14 }} className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-emerald-50 text-emerald-600"><CheckCircle2 className="h-9 w-9" /></motion.div>
                <p className="mt-4 font-display text-xl font-bold text-ink">You&apos;re subscribed</p>
                <p className="mt-2 text-ink-3">The Alert Agent will email you 7 days before {companyName}&apos;s next drive.</p>
              </div>
            ) : (
              <form onSubmit={submit}>
                <span className="grid h-12 w-12 place-items-center rounded-2xl bg-brand-50 text-brand-600"><BellRing className="h-6 w-6" /></span>
                <h3 className="mt-4 font-display text-xl font-bold text-ink">Alerts for {companyName}</h3>
                <p className="mt-1 text-sm text-ink-3">A short summary of the bond terms, confidence and evidence, a week before the drive.</p>
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@college.edu" className="mt-5 h-12 w-full rounded-xl bg-canvas px-4 outline-none ring-1 ring-line focus:ring-2 focus:ring-brand-300" />
                <label className="mt-4 flex cursor-pointer items-start gap-3 text-sm text-ink-2">
                  <input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} className="mt-0.5 h-4 w-4 accent-brand-600" />
                  Also alert me when there&apos;s no bond (otherwise the agent skips low-risk alerts to avoid spam)
                </label>
                {state === "error" && <p className="mt-3 text-sm text-rose-600">{msg}</p>}
                <button disabled={state === "saving"} className="mt-6 w-full rounded-xl bg-ink py-3 font-semibold text-white transition hover:bg-brand-700 disabled:opacity-60">{state === "saving" ? "Saving…" : "Subscribe"}</button>
              </form>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
