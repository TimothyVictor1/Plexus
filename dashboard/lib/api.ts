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

export function headersFor(): HeadersInit {
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
  return handle<T>(await fetch(`${API_BASE}/v1${path}`, { headers: headersFor(), cache: "no-store" }));
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(`${API_BASE}/v1${path}`, {
      method: "POST",
      headers: headersFor(),
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

export type ChangeResult = {
  ok: boolean;
  from_level: number;
  to_level: number;
  reason: string;
  process: ProcessDetail;
};

export type ReviewItem = {
  id: string;
  process_id: string;
  process_name: string;
  kind: string;
  title: string;
  why: string;
  draft_text: string;
  draft_fields: Record<string, unknown>;
  approve_label: string;
  status: "open" | "approved" | "edited" | "skipped" | "executed" | "failed";
  result: { outcome?: string; title?: string; message?: string } | null;
  error: string | null;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
};

export type ReviewDecision = {
  ok: boolean;
  status: ReviewItem["status"];
  title: string;
  detail: string;
  executed: boolean;
};

/** Tell the shell that something which affects its counts has changed, so the nav badge
 *  updates the moment a decision is made rather than at the next poll. */
export const REFRESH_EVENT = "plexus:refresh";

export function signalRefresh() {
  if (typeof window !== "undefined") window.dispatchEvent(new Event(REFRESH_EVENT));
}

export type Insight = {
  kind: "bottleneck" | "change" | "smooth";
  text: string;
  sub: string;
  health: Health;
  process_id: string;
};

export type ConnectedTool = { category: string; connected: boolean };

export type Home = {
  org_name: string;
  is_demo: boolean;
  status: OrgStatus;
  open_reviews: ReviewItem[];
  open_review_count: number;
  insights: Insight[];
  tools: ConnectedTool[];
};

export type Source = { tool: string; title: string; reference: string; kind: string };

export type AskMessage = {
  role: "user" | "assistant";
  text: string;
  sources?: Source[];
  streaming?: boolean;
};

/** Ask a question and receive the answer as it is written. Falls back to a single
 *  response if the browser or the network cannot stream. */
export async function askStream(
  question: string,
  conversationId: string | null,
  onDelta: (chunk: string) => void,
): Promise<{ sources: Source[]; conversationId: string | null; grounded: boolean }> {
  const res = await fetch(`${API_BASE}/v1/ask/stream`, {
    method: "POST",
    headers: headersFor(),
    body: JSON.stringify({ question, conversation_id: conversationId }),
  });

  if (!res.ok || !res.body) {
    const fallback = await post<{
      text: string; sources: Source[]; conversation_id: string | null; grounded: boolean;
    }>("/ask", { question, conversation_id: conversationId });
    onDelta(fallback.text);
    return {
      sources: fallback.sources,
      conversationId: fallback.conversation_id,
      grounded: fallback.grounded,
    };
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let sources: Source[] = [];
  let conversation = conversationId;
  let grounded = true;

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = JSON.parse(line.slice(6));
      if (payload.delta) onDelta(payload.delta);
      if (payload.done) {
        sources = payload.sources ?? [];
        conversation = payload.conversation_id ?? conversation;
        grounded = payload.grounded ?? true;
      }
    }
  }
  return { sources, conversationId: conversation, grounded };
}

export type ConnectorInfo = {
  category: string;
  label: string;
  examples: string;
  status: "connected" | "error" | "not_connected" | "not_configured";
  provider: string;
  detail: string;
  document_count: number;
};

export type ConnectionsView = {
  connections: ConnectorInfo[];
  connected_count: number;
  total: number;
  privacy: { key: string; ok: string; region: string }[];
};

export type ProviderOption = {
  key: string;
  name: string;
  category: string;
  available: boolean;
  reads: string[];
  can_write: boolean;
  transport: string;
  needs: string;
};

export type Catalogue = {
  category: string;
  label: string;
  blurb: string;
  examples: string;
  options: ProviderOption[];
};

export type JobRun = {
  job: string;
  description: string;
  status: string;
  detail: string;
  started_at: string | null;
};

export type Invite = {
  id: string;
  email: string;
  role: string;
  status: string;
  invited_by: string;
  created_at: string;
  expires_at: string;
  link: string;
};
