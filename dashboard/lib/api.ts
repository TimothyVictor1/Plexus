"use client";

const CONFIGURED_API = process.env.NEXT_PUBLIC_PLEXUS_API ?? "";

/** Where the Plexus service is. Unconfigured, the guess is the developer's own machine, which
 *  is right locally and wrong everywhere else — see `serviceOutOfReach` below. */
export const API_BASE = CONFIGURED_API || "http://localhost:8000";

/** Is this console being served from somewhere other than the machine looking at it? */
function servedRemotely(): boolean {
  if (typeof window === "undefined") return false;
  const host = window.location.hostname;
  return host !== "localhost" && host !== "127.0.0.1" && host !== "[::1]";
}

/** A hosted console with no service address configured cannot reach localhost: the browser is
 *  not on the machine that would be serving it, and an https page is not allowed to call http
 *  at all. Attempting it only costs a mixed-content error in the console and a wait for the
 *  timeout, so in that one case go straight to the snapshot. */
function serviceOutOfReach(): boolean {
  return !CONFIGURED_API && servedRemotely();
}

/** Preview mode.
 *
 *  The console is a thin client: every screen reads from the Plexus service. That is the right
 *  architecture and the wrong one for a link someone opens to see what the product is, because
 *  a console with nothing to talk to shows nothing at all.
 *
 *  So preview is a **fallback**, never a default. The console always tries the real service
 *  first. Only when it cannot be reached does it fall back to a captured snapshot, which is
 *  the real output of a real running system written by `scripts/export_snapshot.py`. It is
 *  labelled on every screen and read-only, because anything that changes something needs the
 *  service that is not there.
 *
 *  Making it a fallback rather than a default is what keeps local development working: with
 *  the stack running, the console talks to it, whether or not an address is configured.
 */
let previewMode = false;
let previewChecked: Promise<boolean> | null = null;

export function isPreview(): boolean {
  return previewMode;
}

/** Is a snapshot actually shipped with this build? Asked once. */
async function snapshotAvailable(): Promise<boolean> {
  previewChecked ??= fetch("/preview/org.json", { cache: "force-cache" })
    .then((r) => r.ok)
    .catch(() => false);
  return previewChecked;
}

/** The service could not be reached. Fall back to the snapshot if there is one. */
async function fallBackToPreview(): Promise<boolean> {
  if (previewMode) return true;
  if (!(await snapshotAvailable())) return false;
  previewMode = true;
  if (typeof window !== "undefined") window.dispatchEvent(new Event(REFRESH_EVENT));
  return true;
}

export class PreviewError extends Error {
  constructor(message: string) {
    super(message);
  }
}

const previewCache = new Map<string, unknown>();

async function preview<T>(file: string): Promise<T> {
  const cached = previewCache.get(file);
  if (cached !== undefined) return cached as T;
  const res = await fetch(`/preview/${file}.json`, { cache: "force-cache" });
  if (!res.ok) throw new ApiError(0, OFFLINE_MESSAGE, true);
  const body = (await res.json()) as T;
  previewCache.set(file, body);
  return body;
}

/** Which captured file answers a given request, if any. */
function previewFileFor(path: string): string | null {
  const clean = path.split("?")[0];
  const map: Record<string, string> = {
    "/org": "org",
    "/org/status": "org-status",
    "/home": "home",
    "/processes": "processes",
    "/review": "review",
    "/connections": "connections",
    "/connections/catalogue": "connections-catalogue",
    "/ask/suggestions": "ask-suggestions",
    "/twin": "twin",
    "/insights": "home",
  };
  if (map[clean]) return map[clean];
  const process = clean.match(/^\/processes\/([\w-]+)$/);
  if (process) return `process-${process[1]}`;
  return null;
}

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
  constructor(readonly status: number, message: string, readonly offline = false) {
    super(message);
  }
}

/** The API is a separate service. When it is not reachable, say so in words someone can act
 *  on rather than surfacing a browser-level fetch failure. */
const OFFLINE_MESSAGE =
  "Plexus cannot reach its own service. If you are running it locally, start it with " +
  "'make up'. If this is a hosted copy, the service address has not been set yet.";

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

async function fromSnapshot<T>(path: string): Promise<T> {
  const file = previewFileFor(path);
  if (!file) throw new ApiError(0, OFFLINE_MESSAGE, true);
  const body = await preview<T>(file);
  // The insights screen asks for a list; the captured home holds it alongside the rest.
  if (path.startsWith("/insights")) return (body as { insights: unknown }).insights as T;
  return body;
}

export async function get<T>(path: string): Promise<T> {
  if (previewMode) return fromSnapshot<T>(path);
  if (serviceOutOfReach() && (await fallBackToPreview())) return fromSnapshot<T>(path);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/v1${path}`, { headers: headersFor(), cache: "no-store" });
  } catch {
    if (await fallBackToPreview()) return fromSnapshot<T>(path);
    throw new ApiError(0, OFFLINE_MESSAGE, true);
  }
  return handle<T>(res);
}

/** Answers the what-if screen from the worked scenarios captured with the snapshot. */
async function previewScenario(body: unknown): Promise<unknown> {
  const ask = body as {
    kind: string; person?: string | null; process_id?: string | null; multiplier?: number;
  };
  const key =
    ask.kind === "person_leaves"
      ? `person_leaves:${ask.person}`
      : `demand_changes:${ask.process_id}:${ask.multiplier ?? 2}`;
  const all = await preview<Record<string, unknown>>("twin-scenarios");
  const found = all[key] as TwinScenario | undefined;
  if (found) {
    // The snapshot was captured before scenarios had readings, and holds the scenario alone.
    // Wrap it in the shape the screen now expects, and say plainly that the other readings
    // need a live service rather than pretending the preview can compute them.
    const effects = found.effects ?? [];
    const stops = effects.filter((e) => e.severity === "stops").length;
    const slower = effects.filter((e) => e.severity === "slower").length;
    const bits = [stops && `${stops} would stop`, slower && `${slower} would slow`].filter(
      Boolean,
    ) as string[];
    const answer: TwinAnswer = {
      scenario: found,
      lens: {
        id: "operations",
        label: "How work runs",
        summary: bits.length ? `${bits.join("; ")}.` : "Nothing measurable moves.",
        findings: [],
        unavailable: "",
      },
    };
    return answer;
  }
  throw new PreviewError(
    "This preview holds a set of worked examples. Connect a Plexus service to ask anything.",
  );
}

function previewRefusal(): PreviewError {
  return new PreviewError(
    "This is a preview of an example company, so nothing here can be changed. " +
      "Connect a Plexus service to use it for real.",
  );
}

export async function post<T>(path: string, body?: unknown): Promise<T> {
  if (!previewMode && serviceOutOfReach()) await fallBackToPreview();
  if (previewMode) {
    if (path === "/twin/what-if") return (await previewScenario(body)) as T;
    throw previewRefusal();
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/v1${path}`, {
      method: "POST",
      headers: headersFor(),
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    if (await fallBackToPreview()) {
      if (path === "/twin/what-if") return (await previewScenario(body)) as T;
      throw previewRefusal();
    }
    throw new ApiError(0, OFFLINE_MESSAGE, true);
  }
  return handle<T>(res);
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
  // Every answer is computed against a company's own records, which a static snapshot does
  // not have. Saying so is better than returning something that reads like an answer.
  const cannotAnswerHere = () => {
    onDelta(
      "Answers are worked out from your company's own records, so this needs a running " +
        "Plexus service rather than a preview. Everything else on this page is real output " +
        "from an example company.",
    );
    return { sources: [] as Source[], conversationId: null, grounded: false };
  };

  if (!previewMode && serviceOutOfReach()) await fallBackToPreview();
  if (previewMode) return cannotAnswerHere();

  let res: Response;
  try {
    res = await fetch(`${API_BASE}/v1/ask/stream`, {
      method: "POST",
      headers: headersFor(),
      body: JSON.stringify({ question, conversation_id: conversationId }),
    });
  } catch {
    if (await fallBackToPreview()) return cannotAnswerHere();
    throw new ApiError(0, OFFLINE_MESSAGE, true);
  }

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

export type StepRole = {
  process_id: string;
  process_name: string;
  step: string;
  verb: string;
  events: number;
  share: number;
  others: number;
};

export type PersonModel = {
  token: string;
  label: string;
  events: number;
  processes: string[];
  roles: StepRole[];
};

export type StepLoad = {
  verb: string;
  label: string;
  events: number;
  people: number;
  per_week: number;
  top_share: number;
};

export type TwinProcess = {
  id: string;
  name: string;
  cases: number;
  people: number;
  steps: StepLoad[];
  cycle: Duration;
};

export type TwinRisk = {
  kind: "key_person" | "single_point" | "concentration";
  person: string;
  process_name: string;
  step: string;
  share: number;
  text: string;
};

export type OrgModel = {
  window_days: number;
  people: PersonModel[];
  processes: TwinProcess[];
  external_parties: number;
  total_events: number;
  risks: TwinRisk[];
};

export type TwinEffect = {
  process_id: string;
  process_name: string;
  step: string;
  severity: "stops" | "slower" | "fine";
  text: string;
  before: Duration | null;
  after: Duration | null;
};

export type TwinScenario = {
  kind: string;
  title: string;
  summary: string;
  effects: TwinEffect[];
  assumptions: string[];
  cover: string[];
  magnitude?: number | null;
};

/** One of the readings a scenario can be asked for. */
export type TwinLensOption = { id: string; label: string; blurb: string };

export type TwinLensFinding = { label: string; value: string; detail: string };

/** The chosen reading. `unavailable` is set when the records cannot answer it, and the screen
 *  shows that instead of findings — an empty answer always says why it is empty. */
export type TwinLensView = {
  id: string;
  label: string;
  summary: string;
  findings: TwinLensFinding[];
  unavailable: string;
};

/** What the service returns: the same scenario, plus the reading that was asked for. */
export type TwinAnswer = { scenario: TwinScenario; lens: TwinLensView };

/* ------------------------------------------------------- the twins of a company */

/** One view of the company. `general` places the others side by side. */
export type TwinKind = { id: string; label: string; blurb: string; requires: string[] };

/** Whether a twin can be built from what this company has connected, and what is missing. */
export type Readiness = { ready: boolean; reason: string; needs: string[] };

export type TwinCard = {
  id: string;
  label: string;
  blurb: string;
  readiness: Readiness;
  headline: string;
  figures: string[];
};

export type GeneralTwin = {
  window_days: number;
  people: number;
  processes: number;
  events: number;
  summary: string;
  cards: TwinCard[];
};

export type MoneyAtRest = {
  process_id: string;
  process_name: string;
  currency: string;
  total: number;
  records: number;
  waits_at: string;
  wait: { seconds: number; text: string } | null;
  note: string;
};

export type FinancialTwin = {
  window_days: number;
  currencies: string[];
  at_rest: MoneyAtRest[];
  without_amounts: string[];
  summary: string;
  ready: boolean;
  reason: string;
};

export type Handover = {
  process_id: string;
  process_name: string;
  step: string;
  events: number;
  share: number;
  others: number;
  urgency: string;
  note: string;
};

export type PersonTwin = {
  token: string;
  label: string;
  events: number;
  processes: string[];
  handover: Handover[];
  overlaps_with: string[];
  summary: string;
};

export type PeopleTwin = {
  window_days: number;
  people: PersonTwin[];
  only_one_person: number;
  summary: string;
};

/* --------------------------------------------- the shadow workforce's record */

/** One agent's record on one process. Accuracy counts only settled predictions. */
export type Scorecard = {
  process_id: string;
  process_name: string;
  agent: string;
  predictions: number;
  settled: number;
  agreed: number;
  edited: number;
  rejected: number;
  accuracy: number;
  weighted: number;
  ready: boolean;
  needs: number;
  verdict_text: string;
};

export type Scoreboard = { window_days: number; cards: Scorecard[]; summary: string };

/** One thing an agent would have done, and what the person did instead. */
export type ShadowRun = {
  id: string;
  process_id: string;
  agent: string;
  trigger_kind: string;
  predicted: Record<string, unknown>;
  predicted_at: string;
  confidence: number;
  verdict: "pending" | "agreed" | "edited" | "rejected" | "expired";
  observed: Record<string, unknown> | null;
  observed_at: string | null;
  note: string;
};
