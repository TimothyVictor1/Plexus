"use client";

export const API_BASE =
  process.env.NEXT_PUBLIC_PLEXUS_API ?? "http://localhost:8000";

export type Role = "viewer" | "operator" | "approver" | "admin";

/** The role the console acts as. OIDC replaces this when auth lands; until then the API still
 *  enforces the role on every request, so a viewer genuinely cannot approve. */
export function currentRole(): Role {
  if (typeof window === "undefined") return "approver";
  try {
    return (window.localStorage.getItem("plexus.role") as Role) ?? "approver";
  } catch {
    return "approver";
  }
}

export function setRole(role: Role) {
  try {
    window.localStorage.setItem("plexus.role", role);
  } catch {
    /* private window: the header default applies */
  }
}

function headers(): HeadersInit {
  return {
    "content-type": "application/json",
    "x-plexus-tenant": "nordvik",
    "x-plexus-subject": "anna.lindqvist",
    "x-plexus-role": currentRole(),
  };
}

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      /* keep the status line */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export async function get<T>(path: string): Promise<T> {
  return handle<T>(await fetch(`${API_BASE}/v1${path}`, { headers: headers(), cache: "no-store" }));
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(`${API_BASE}/v1${path}`, {
      method: "POST",
      headers: headers(),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

/* ------------------------------------------------------------------ shapes */
export type Overview = {
  tenant: { id: string; paused: boolean };
  documents: number;
  documents_by_kind: Record<string, number>;
  events: number;
  graph: Record<string, number>;
  graph_nodes: number;
  vault_entries: number;
  pending_actions: number;
  adapter_writes: number;
  model_calls: { count: number; cost_usd: number; avg_latency_ms: number };
  chains: { process_id: string; ok: boolean; entries: number; broken_at: number | null }[];
  chain_ok: boolean;
  processes: {
    id: string; name: string; tier: string; paused: boolean; case_count: number;
    metrics: Record<string, number | string>;
  }[];
};

export type Trust = {
  trust: number; approval_rate: number; reversal_rate: number; recency: number;
  blast_radius: number; samples: number; executions: number; reversals: number;
  days_since_error: number | null; terms: Record<string, number>;
};

export type ProcessDetail = {
  id: string; name: string; description: string;
  steps: { name: string; verb: string; frequency: number; median_duration_s: number; actors: string[]; ordinal: number }[];
  edges: { source: string; target: string; count: number; median_gap_s: number; dependency: number }[];
  metrics: Record<string, number | string>;
  case_count: number; tier: string; paused: boolean;
  trust: Trust;
  transition: { direction: string; from_tier: string; to_tier: string; reason: string; eligible: boolean; blockers: string[] };
  thresholds: Record<string, number>;
  min_samples: Record<string, number>;
};

export type Verdict = {
  id: string; decision: "approve" | "reject" | "escalate";
  reasons: { kind: string; ref: string; text: string }[];
  verifier_model: { vendor: string; model: string };
};

export type Simulation = {
  changes: { kind: string; op: string; label_or_type: string; key: string }[];
  violations: { rule_id: string; rule_name: string; effect: string; evidence: string }[];
  blast_radius: { records_touched: number; money_touched: number; external_parties: number; normalised: number };
  summary: string;
};

export type InboxItem = {
  id: string; process_id: string; operation: string; arguments: Record<string, unknown>;
  rationale: string; risk_class: string;
  cited_context: { key: string; kind: string; why: string }[];
  simulation: Simulation | null;
  actor_model: { vendor: string; model: string };
  created_at: string;
  verdict: Verdict | null;
};

export type Outcome = {
  outcome: "executed" | "held" | "refused";
  entry_type: string; title: string; detail: string;
  write_result?: { ok: boolean; message: string };
};

export type RunResult = {
  action: InboxItem & { id: string };
  simulation: Simulation;
  verdict: Verdict;
  outcome: Outcome;
  tier: string;
};

export type LedgerEntry = {
  seq: number; id: string; process_id: string; entry_type: string;
  actor: { kind: string; id: string; role?: string };
  payload: Record<string, unknown>; ts: string; prev_hash: string; hash: string;
};

export const TIERS = ["OBSERVE", "EXPLAIN", "SUGGEST", "ACT_WITH_APPROVAL", "AUTONOMOUS"] as const;
