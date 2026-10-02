import type { Risk } from "./api";

/** 150000 -> "₹1,50,000" (Indian digit grouping). */
export function inr(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return "₹" + Math.round(n).toLocaleString("en-IN");
}

/** 150000 -> "₹1.5 L", 12000000 -> "₹1.2 Cr" */
export function inrShort(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  if (n >= 1e7) return `₹${+(n / 1e7).toFixed(2)} Cr`;
  if (n >= 1e5) return `₹${+(n / 1e5).toFixed(2)} L`;
  if (n >= 1e3) return `₹${+(n / 1e3).toFixed(1)}K`;
  return `₹${n}`;
}

export function months(n: number | null | undefined): string {
  if (!n) return "—";
  if (n % 12 === 0) return `${n / 12} yr${n > 12 ? "s" : ""}`;
  return `${n} mo`;
}

export function dateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso.length <= 10 ? iso + "T00:00:00" : iso);
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
}

export function relativeDays(days: number): string {
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return `in ${days} days`;
}

export function shortName(name: string): string {
  return name.replace(/\b(Private|Pvt\.?|Limited|Ltd\.?|LLP)\b/gi, "").replace(/[\s.,]+$/g, "").replace(/\s+/g, " ").trim();
}

export function initials(name: string): string {
  const words = shortName(name).split(" ").filter(Boolean);
  return (words[0]?.[0] ?? "?") + (words[1]?.[0] ?? "");
}

const GRADIENTS = [
  "from-indigo-500 to-violet-600",
  "from-sky-500 to-indigo-600",
  "from-emerald-500 to-teal-600",
  "from-rose-500 to-pink-600",
  "from-amber-500 to-orange-600",
  "from-fuchsia-500 to-purple-600",
  "from-cyan-500 to-blue-600",
  "from-lime-500 to-emerald-600",
];

export function companyGradient(id: number): string {
  return GRADIENTS[id % GRADIENTS.length];
}

const COVERS = ["office", "team", "meeting", "workshop", "coding", "laptop", "students-laptop", "study-group"];
export function companyCover(id: number): string {
  return `/images/${COVERS[id % COVERS.length]}.jpg`;
}

export const RISK_STYLE: Record<Risk["level"], { label: string; color: string; bg: string; text: string; ring: string }> = {
  low: { label: "Low risk", color: "var(--status-good)", bg: "bg-emerald-50", text: "text-emerald-700", ring: "ring-emerald-200" },
  moderate: { label: "Moderate risk", color: "var(--status-warning)", bg: "bg-amber-50", text: "text-amber-700", ring: "ring-amber-200" },
  high: { label: "High risk", color: "var(--status-critical)", bg: "bg-rose-50", text: "text-rose-700", ring: "ring-rose-200" },
  unknown: { label: "No data yet", color: "#94a3b8", bg: "bg-slate-100", text: "text-slate-600", ring: "ring-slate-200" },
};

export const FIELD_LABELS: Record<string, string> = {
  company_name: "Company",
  batch_year: "Batch",
  role: "Role",
  ctc_annual: "Annual CTC",
  has_bond: "Has a bond",
  bond_months: "Bond period",
  penalty_amount: "Bond penalty",
  penalty_prorated: "Pro-rated?",
  notice_days: "Notice period",
  training_cost_recovery: "Training cost recovered",
  certificates_retained: "Certificates kept",
  other_risky_clauses: "Other risky clauses",
  public_summary: "Public source summary",
};

export function fieldValue(field: string, v: unknown): string {
  if (v === null || v === undefined || (Array.isArray(v) && v.length === 0)) return field === "other_risky_clauses" ? "None found" : "Not stated";
  if (field === "ctc_annual" || field === "penalty_amount") return inr(v as number);
  if (field === "bond_months") return `${v} months`;
  if (field === "notice_days") return `${v} days`;
  if (field === "penalty_prorated") return v === "yes" ? "Yes, reduced for time served" : v === "no" ? "No, full amount" : "Not mentioned";
  if (typeof v === "boolean") return v ? "Yes" : "No";
  if (Array.isArray(v)) return v.join(", ");
  return String(v);
}

export const DECISION_STYLE: Record<string, { label: string; tone: string; text: string }> = {
  corroborate: { label: "Corroborated", tone: "bg-emerald-50 text-emerald-700 ring-emerald-200", text: "Matches earlier uploads" },
  variant: { label: "New variant", tone: "bg-sky-50 text-sky-700 ring-sky-200", text: "Different batch or role, stored separately" },
  conflict: { label: "Conflict", tone: "bg-amber-50 text-amber-800 ring-amber-200", text: "Different terms for the same batch and role" },
  outlier: { label: "Outlier", tone: "bg-rose-50 text-rose-700 ring-rose-200", text: "Unusual values, held for review" },
  new_company: { label: "New company", tone: "bg-violet-50 text-violet-700 ring-violet-200", text: "Created and flagged for review" },
};
