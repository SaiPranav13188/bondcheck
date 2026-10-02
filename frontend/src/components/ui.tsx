"use client";

import { animate, motion, useInView, useMotionValue, useTransform } from "framer-motion";
import { AlertTriangle, CheckCircle2, CircleHelp, ShieldAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { Risk } from "@/lib/api";
import { companyGradient, initials, RISK_STYLE } from "@/lib/format";

// ------------------------------------------------------------------ motion helpers
export function Reveal({ children, delay = 0, y = 24, className = "" }: { children: ReactNode; delay?: number; y?: number; className?: string }) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: "-60px" }}
      transition={{ duration: 0.6, delay, ease: [0.21, 0.6, 0.35, 1] }}
    >
      {children}
    </motion.div>
  );
}

export function CountUp({ to, format = (n) => Math.round(n).toLocaleString("en-IN"), duration = 1.6 }: { to: number; format?: (n: number) => string; duration?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const inView = useInView(ref, { once: true });
  const mv = useMotionValue(0);
  const text = useTransform(mv, (v) => format(v));
  useEffect(() => {
    if (!inView) return;
    const c = animate(mv, to, { duration, ease: [0.16, 1, 0.3, 1] });
    return () => c.stop();
  }, [inView, to, duration, mv]);
  return <motion.span ref={ref}>{text}</motion.span>;
}

// ------------------------------------------------------------------ data hook
export function useApi<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [nonce, setNonce] = useState(0);
  const key = `${JSON.stringify(deps)}:${nonce}`;
  const [res, setRes] = useState<{ key: string; data: T | null; error: string | null }>({ key: "", data: null, error: null });
  useEffect(() => {
    let live = true;
    loader()
      .then((data) => { if (live) setRes({ key, data, error: null }); })
      .catch((e: Error) => { if (live) setRes((r) => ({ key, data: r.data, error: e.message || "Something went wrong" })); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- `key` captures deps
  }, [key]);
  const reload = useCallback(() => setNonce((n) => n + 1), []);
  // While a new request is in flight the previous data stays visible.
  return { data: res.data, error: res.key === key ? res.error : null, loading: res.key !== key, reload };
}

// ------------------------------------------------------------------ small pieces
export function Monogram({ id, name, size = "md" }: { id: number; name: string; size?: "sm" | "md" | "lg" | "xl" }) {
  const s = { sm: "h-9 w-9 text-xs rounded-xl", md: "h-12 w-12 text-sm rounded-2xl", lg: "h-16 w-16 text-lg rounded-2xl", xl: "h-20 w-20 text-2xl rounded-3xl" }[size];
  return (
    <span className={`relative grid shrink-0 place-items-center bg-linear-to-br font-display font-bold uppercase text-white shadow-lg ${companyGradient(id)} ${s}`}>
      <span className="absolute inset-0 rounded-[inherit] bg-[radial-gradient(circle_at_30%_20%,rgba(255,255,255,0.35),transparent_60%)]" />
      <span className="relative">{initials(name)}</span>
    </span>
  );
}

const RISK_ICON = { low: CheckCircle2, moderate: AlertTriangle, high: ShieldAlert, unknown: CircleHelp };

export function RiskBadge({ risk, size = "sm" }: { risk?: Risk | null; size?: "sm" | "md" }) {
  const level = risk?.level ?? "unknown";
  const st = RISK_STYLE[level];
  const Icon = RISK_ICON[level];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full font-semibold ring-1 ${st.bg} ${st.text} ${st.ring} ${size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm"}`}>
      <Icon className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} aria-hidden />
      {st.label}
    </span>
  );
}

/** Radial 0-100 score. Status colour + icon + label, never colour alone. */
export function RiskMeter({ risk, size = 72, stroke = 7, showLabel = false }: { risk?: Risk | null; size?: number; stroke?: number; showLabel?: boolean }) {
  const level = risk?.level ?? "unknown";
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className="relative" style={{ width: size, height: size }} role="img" aria-label={`Bond risk score ${risk?.score ?? "unknown"} out of 100, ${RISK_STYLE[level].label}`}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#eef0f6" strokeWidth={stroke} />
          <motion.circle
            cx={size / 2} cy={size / 2} r={r} fill="none" stroke={RISK_STYLE[level].color} strokeWidth={stroke} strokeLinecap="round"
            strokeDasharray={c}
            initial={{ strokeDashoffset: c }}
            whileInView={{ strokeDashoffset: c * (1 - (risk?.score ?? 0) / 100) }}
            viewport={{ once: true }}
            transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
          />
        </svg>
        <div className="absolute inset-0 grid place-items-center">
          <span className="font-display font-bold text-ink" style={{ fontSize: size * 0.28 }}>{risk?.score ?? "–"}</span>
        </div>
      </div>
      {showLabel && <RiskBadge risk={risk} />}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`skeleton block ${className}`} />;
}

export function ConfidencePill({ level, uploads }: { level: string; uploads?: number }) {
  const dots = { none: 0, low: 1, medium: 2, high: 3 }[level] ?? 0;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-ink-2" title="Confidence grows with the number of verified uploads">
      <span className="flex gap-0.5">
        {[0, 1, 2].map((i) => <span key={i} className={`h-1.5 w-3 rounded-full ${i < dots ? "bg-brand-500" : "bg-slate-300"}`} />)}
      </span>
      {level === "none" ? "No data" : `${level[0].toUpperCase()}${level.slice(1)} confidence`}
      {uploads !== undefined && <span className="text-ink-3">· {uploads} upload{uploads === 1 ? "" : "s"}</span>}
    </span>
  );
}

export function SectionHeading({ eyebrow, title, sub, center = false, light = false }: { eyebrow?: string; title: ReactNode; sub?: ReactNode; center?: boolean; light?: boolean }) {
  return (
    <Reveal className={`max-w-2xl ${center ? "mx-auto text-center" : ""}`}>
      {eyebrow && <p className={`mb-3 text-xs font-bold uppercase tracking-[0.18em] ${light ? "text-brand-300" : "text-brand-600"}`}>{eyebrow}</p>}
      <h2 className={`font-display text-3xl font-bold leading-tight sm:text-4xl ${light ? "text-white" : "text-ink"}`}>{title}</h2>
      {sub && <p className={`mt-4 text-base leading-relaxed sm:text-lg ${light ? "text-slate-300" : "text-ink-2"}`}>{sub}</p>}
    </Reveal>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="card flex flex-col items-center gap-3 p-10 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-2xl bg-rose-50 text-rose-600"><AlertTriangle className="h-6 w-6" /></div>
      <p className="font-semibold text-ink">Couldn&apos;t reach the BondCheck API</p>
      <p className="max-w-md text-sm text-ink-3">{message}. Make sure the backend is running (<code className="rounded bg-slate-100 px-1">uvicorn api.main:app</code>).</p>
      {onRetry && <button onClick={onRetry} className="rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">Try again</button>}
    </div>
  );
}

export function Disclaimer({ className = "" }: { className?: string }) {
  return (
    <p className={`text-xs text-ink-3 ${className}`}>
      Information from uploaded letters, not legal advice. Terms are shown as reported, not as claims about the company.
    </p>
  );
}
