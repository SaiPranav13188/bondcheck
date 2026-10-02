"use client";

import { AnimatePresence, motion } from "framer-motion";
import { BadgeCheck, EyeOff, FileSearch, ShieldCheck, TriangleAlert } from "lucide-react";
import { useEffect, useState } from "react";

/** Animated offer letter: the agents scan it, redact PII and pin the bond terms with evidence. */
export default function HeroLetter() {
  const [step, setStep] = useState(0); // 0 scan, 1 redact, 2 extract, 3 verified
  useEffect(() => {
    const t = setInterval(() => setStep((s) => (s + 1) % 5), 1900);
    return () => clearInterval(t);
  }, []);
  const redacted = step >= 1 && step < 4;
  const highlight = step >= 2 && step < 4;
  const verified = step === 3;

  return (
    <div className="relative mx-auto w-full max-w-[460px]">
      {/* back sheets */}
      <div className="absolute inset-x-6 -bottom-4 top-6 rotate-[4deg] rounded-3xl bg-white/50 shadow-xl ring-1 ring-slate-200/70" />
      <div className="absolute inset-x-3 -bottom-2 top-3 -rotate-[2deg] rounded-3xl bg-white/70 shadow-xl ring-1 ring-slate-200/70" />

      <motion.div
        initial={{ opacity: 0, y: 30, rotate: -2 }}
        animate={{ opacity: 1, y: 0, rotate: 0 }}
        transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        className="relative overflow-hidden rounded-3xl bg-white p-6 shadow-[0_30px_80px_-20px_rgba(30,27,75,0.35)] ring-1 ring-slate-200 sm:p-7"
      >
        {/* scan beam */}
        <AnimatePresence>
          {step === 0 && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="pointer-events-none absolute inset-x-0 z-10 h-20 animate-scan bg-linear-to-b from-transparent via-brand-400/25 to-transparent">
              <div className="absolute inset-x-0 top-1/2 h-px bg-brand-500 shadow-[0_0_12px_2px_rgba(99,102,241,0.7)]" />
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex items-start justify-between">
          <div>
            <p className="font-display text-sm font-extrabold tracking-wide text-brand-800">NEXORA TECHNOLOGIES PVT. LTD.</p>
            <p className="text-[11px] text-slate-400">Tech Park, Hyderabad · Ref NEX/HR/2026/412</p>
          </div>
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-50 font-display text-xs font-bold text-brand-700">NX</div>
        </div>

        <div className="mt-5 space-y-1 text-[12.5px] leading-relaxed text-slate-600">
          <p>To,</p>
          <p><Redact on={redacted} w="w-28">Mr. Rohan Iyer</Redact></p>
          <p><Redact on={redacted} w="w-40">H.No. 12-4, MG Road, Pune</Redact></p>
          <p className="pt-1">Contact: <Redact on={redacted} w="w-24">+91 98xxxx3210</Redact></p>
        </div>

        <p className="mt-4 text-[12.5px] font-semibold text-ink">Subject: Offer of Employment, 2026 Batch</p>
        <div className="mt-3 space-y-2.5 text-[12.5px] leading-relaxed text-slate-600">
          <p>Dear <Redact on={redacted} w="w-12">Rohan</Redact>, we are pleased to offer you the position of <Mark on={highlight} tone="sky">Graduate Engineer Trainee</Mark> with an annual CTC of <Mark on={highlight} tone="sky">Rs. 4,00,000</Mark>.</p>
          <p>1. You will be on probation for six months.</p>
          <p>2. You shall serve the Company for a minimum period of <Mark on={highlight} tone="amber">24 months</Mark>, failing which you shall pay liquidated damages of <Mark on={highlight} tone="rose">Rs. 1,50,000/-</Mark>.</p>
          <p>3. Original certificates will be <Mark on={highlight} tone="amber">retained</Mark> until the bond period ends.</p>
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-dashed border-slate-200 pt-4 text-[11px] text-slate-400">
          <span>Accepted by: <Redact on={redacted} w="w-20">Rohan Iyer</Redact></span>
          <span className="font-mono">page 1 / 2</span>
        </div>

        {/* verified stamp */}
        <AnimatePresence>
          {verified && (
            <motion.div initial={{ scale: 2, opacity: 0, rotate: -20 }} animate={{ scale: 1, opacity: 1, rotate: -12 }} exit={{ opacity: 0 }} transition={{ type: "spring", stiffness: 300, damping: 18 }}
              className="absolute bottom-16 right-6 rounded-xl border-[3px] border-emerald-500 px-3 py-1 font-display text-sm font-extrabold uppercase tracking-wider text-emerald-600">
              Evidence verified
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* floating agent chips */}
      <Chip className="-left-6 top-40 sm:-left-14" show={step >= 1 && step < 4} icon={<EyeOff className="h-4 w-4" />} tone="bg-ink text-white" title="Privacy Agent" sub="7 personal details redacted" />
      <Chip className="-right-4 top-60 sm:-right-16" show={step >= 2 && step < 4} icon={<FileSearch className="h-4 w-4" />} tone="bg-white text-ink" title="Bond: 24 months" sub="quote verified ✓" />
      <Chip className="-left-4 bottom-24 sm:-left-16" show={step >= 2 && step < 4} icon={<TriangleAlert className="h-4 w-4 text-rose-500" />} tone="bg-white text-ink" title="Penalty ₹1,50,000" sub="not pro-rated" />
      <Chip className="-right-2 -bottom-5 sm:-right-10" show={verified} icon={<BadgeCheck className="h-4 w-4 text-emerald-500" />} tone="bg-white text-ink" title="Corroborated" sub="matches 7 uploads" />

      <div className="absolute -top-5 left-1/2 flex -translate-x-1/2 items-center gap-2 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-ink shadow-lg ring-1 ring-slate-200">
        <span className="relative flex h-2 w-2"><span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" /><span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" /></span>
        {["Reading letter…", "Redacting personal data…", "Extracting with evidence…", "Verified against 7 uploads", "Document deleted"][step]}
        <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
      </div>
    </div>
  );
}

function Redact({ on, children }: { on: boolean; w?: string; children: React.ReactNode }) {
  return (
    <span className="relative inline-block align-middle">
      <span className={on ? "opacity-0" : "opacity-100 transition-opacity duration-300"}>{children}</span>
      <motion.span className="absolute inset-y-px -left-0.5 -right-0.5 rounded-[3px] bg-ink" initial={false} animate={{ scaleX: on ? 1 : 0 }} style={{ originX: 0 }} transition={{ duration: 0.45, ease: "easeOut" }} />
    </span>
  );
}

const TONES = { sky: "bg-sky-200/70", amber: "bg-amber-200/80", rose: "bg-rose-200/80" };
function Mark({ on, tone, children }: { on: boolean; tone: keyof typeof TONES; children: React.ReactNode }) {
  return (
    <span className="relative inline-block whitespace-nowrap">
      <motion.span className={`absolute -inset-x-0.5 inset-y-0 rounded ${TONES[tone]}`} initial={false} animate={{ scaleX: on ? 1 : 0 }} style={{ originX: 0 }} transition={{ duration: 0.5, ease: "easeOut" }} />
      <span className={`relative ${on ? "font-semibold text-ink" : ""}`}>{children}</span>
    </span>
  );
}

function Chip({ show, icon, title, sub, tone, className }: { show: boolean; icon: React.ReactNode; title: string; sub: string; tone: string; className: string }) {
  return (
    <AnimatePresence>
      {show && (
        <motion.div initial={{ opacity: 0, scale: 0.85, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.9 }} transition={{ type: "spring", stiffness: 260, damping: 20 }}
          className={`absolute z-20 flex items-center gap-2.5 rounded-2xl px-3.5 py-2.5 shadow-xl ring-1 ring-slate-200/60 ${tone} ${className}`}>
          <span className="grid h-8 w-8 place-items-center rounded-xl bg-slate-100/20 ring-1 ring-current/10">{icon}</span>
          <span className="leading-tight">
            <span className="block text-[13px] font-semibold">{title}</span>
            <span className="block text-[11px] opacity-70">{sub}</span>
          </span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
