"use client";

export const API_BASE = process.env.NEXT_PUBLIC_PLEXUS_API ?? "http://localhost:8000";

export type Role = "viewer" | "operator" | "approver" | "admin";

/** Which org the console is looking at. Replaced by the OIDC token when auth lands; the API
 *  validates the tenant either way, so this cannot be used to reach another company's data. */
export function currentTenant(): string {
  if (typeof window === "undefined") return "demo";
  try {
    return window.localStorage.getItem("plexus.tenant") ?? "demo";
  } catch {
    return "demo";
  }
}

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
    /* private window: the server default applies */
  }
}

function headers(): HeadersInit {
  return {
    "content-type": "application/json",
    "x-plexus-tenant": currentTenant(),
    "x-plexus-subject": "console-user",
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
export type Org = {
  id: string;
  name: string;
  display_name: string;
  locale: string;
  is_demo: boolean;
  paused: boolean;
  created_at: string;
};

export type Stage = "no_connections" | "learning" | "ready";

export type OrgStatus = {
  stage: Stage;
  connected_count: number;
  process_count: number;
  review_count: number;
  ready_min_cases: number;
};

export type Duration = { seconds: number; text: string };
export type Health = "smooth" | "watch" | "slow";

export type Slowest = {
  from_step: string;
  to_step: string;
  text: string;
  duration: Duration | null;
};

export type ProcessSummary = {
  id: string;
  name: string;
  description: string;
  total_duration: Duration;
  health: Health;
  slowest: Slowest;
  level: number;
  paused: boolean;
  case_count: number;
  tools: string[];
  tools_text: string;
};

export type Step = { label: string; order: number; verb: string };
export type Wait = {
  from_step: string;
  to_step: string;
  duration: Duration;
  is_slowest: boolean;
};

export type Autonomy = {
  level: number;
  level_key: string;
  decisions: number;
  needed: number;
  can_promote: boolean;
  reason: string;
  paused: boolean;
};

export type Technical = {
  cases: number;
  variants: number;
  median_gaps: { from: string; to: string; seconds: number; count: number; dependency: number }[];
  bottleneck_transition: string;
  trust_score: number;
  trust_components: Record<string, number>;
  tier: string;
};

export type ProcessDetail = ProcessSummary & {
  steps: Step[];
  waits: Wait[];
  help_tip: string;
  autonomy: Autonomy;
  technical: Technical;
};

export const LEVEL_KEYS = ["watches", "explains", "suggests", "actsWithOk", "actsAlone"] as const;
