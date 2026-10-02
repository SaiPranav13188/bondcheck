export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

// ------------------------------------------------------------------ types
export type Risk = { score: number | null; level: "low" | "moderate" | "high" | "unknown"; factors: string[] };

export type GroupStats = {
  uploads: number;
  bond_share: number | null;
  typical_bond_months: number | null;
  typical_penalty: number | null;
  penalty_values: Record<string, number>;
  prorated: "yes" | "no" | "not_mentioned" | null;
  typical_notice_days: number | null;
  median_ctc: number | null;
  ctc_range: [number, number] | null;
  certificates_retained_share: number | null;
  training_recovery_share: number | null;
  risky_clauses: { clause: string; count: number }[];
  latest_upload: string | null;
  risk: Risk;
};

export type CompanyCard = {
  id: number;
  name: string;
  aliases: string[];
  latest_batch: number | null;
  verified_uploads: number;
  summary: GroupStats | null;
  open_conflicts: number;
  public_sources: number;
  next_drive: string | null;
  roles: string[];
  confidence: "none" | "low" | "medium" | "high";
};

export type Evidence = { field: string; quote: string };

export type OfferRecord = {
  id: number;
  company_id: number;
  batch_year: number;
  role: string | null;
  ctc_annual: number | null;
  has_bond: boolean | null;
  bond_months: number | null;
  penalty_amount: number | null;
  penalty_prorated: "yes" | "no" | "not_mentioned";
  notice_days: number | null;
  training_cost_recovery: boolean | null;
  certificates_retained: boolean | null;
  other_risky_clauses: string[];
  confidence: number;
  status: string;
  created_at: string;
  evidence: Evidence[];
  company_name?: string;
};

export type Conflict = {
  id: number;
  company_id: number;
  batch_year: number;
  role: string | null;
  field: string;
  values_seen: Record<string, number>;
  status: string;
  created_at: string;
  name?: string;
};

export type CompanyDetail = {
  company: { id: number; name: string; aliases: string[]; created_at: string };
  confidence: string;
  trend: { from_batch: number; to_batch: number; penalty_change: number; bond_months_change: number; direction: string } | null;
  conflicts: Conflict[];
  verified_uploads: number;
  batches: Record<string, { all: GroupStats; roles: Record<string, GroupStats> }>;
  timeline: { batch: number; typical_penalty: number | null; typical_bond_months: number | null; uploads: number; median_ctc: number | null }[];
  records: OfferRecord[];
  public_sources: { id: number; batch_year: number; has_bond: boolean | null; bond_months: number | null; penalty_amount: number | null; source_url: string; created_at: string; summary: string | null }[];
  drives: { id: number; college: string; drive_date: string }[];
  data_requests: { id: number; message: string; reason: string }[];
  pending_uploads: number;
  latest_upload: string | null;
};

export type Stats = {
  companies: number;
  verified_uploads: number;
  bond_share: number;
  median_penalty: number;
  max_penalty: number;
  open_conflicts: number;
  letters_processed: number;
  pii_redacted: number;
  drives_next_30_days: number;
};

export type Drive = {
  id: number;
  company_id: number;
  college: string;
  drive_date: string;
  name: string;
  days_left: number;
  coverage: { gap: "no_data" | "stale" | "conflict" | null; latest_batch: number | null; uploads: number; open_conflicts: number };
};

export type AgentEvent = {
  agent?: string;
  kind: string;
  message?: string;
  t?: number;
  data?: Record<string, unknown>;
  result?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
};

export type FieldResult = { value: unknown; quote: string; confidence: number; source: string; checks: string[] };

export type UploadResult = {
  upload_id: string;
  status: "needs_confirmation" | "stored" | "queued" | "rejected" | "escalated";
  message: string;
  decision?: string | null;
  decision_detail?: Record<string, unknown> | null;
  record_id?: number | null;
  company_id?: number | null;
  questions?: { field: string; question: string; current: unknown; quote?: string; type: string }[];
  extracted?: Record<string, FieldResult>;
  privacy_report?: { passed: boolean; attempts: number; redactions: number };
  tokens?: number;
};

export type Sample = { key: string; title: string; description: string; expect: string; scanned: boolean };

// ------------------------------------------------------------------ fetch helpers
export async function getJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(text || `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export async function postJSON<T>(path: string, body: unknown, headers: Record<string, string> = {}): Promise<T> {
  return getJSON<T>(path, { method: "POST", headers: { "content-type": "application/json", ...headers }, body: JSON.stringify(body) });
}

/** Reads an NDJSON stream of agent events, calling onEvent for each line. */
export async function streamEvents(
  path: string,
  init: RequestInit,
  onEvent: (e: AgentEvent) => void,
): Promise<AgentEvent | null> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => "");
    let msg = text;
    try {
      msg = JSON.parse(text).detail ?? text;
    } catch {}
    throw new Error(msg || `${res.status} ${res.statusText}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let last: AgentEvent | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      const ev = JSON.parse(line) as AgentEvent;
      last = ev;
      onEvent(ev);
    }
  }
  if (buffer.trim()) {
    last = JSON.parse(buffer) as AgentEvent;
    onEvent(last);
  }
  return last;
}
