"use client";

import type { ReactNode } from "react";

export function Panel({
  title, actions, children, flush = false,
}: { title?: ReactNode; actions?: ReactNode; children: ReactNode; flush?: boolean }) {
  return (
    <section className="panel">
      {(title || actions) && (
        <header>
          {typeof title === "string" ? <h2>{title}</h2> : title}
          {actions && <div className="inline">{actions}</div>}
        </header>
      )}
      <div className={flush ? "body flush" : "body"}>{children}</div>
    </section>
  );
}

export function Tile({
  label, value, note, tone,
}: { label: string; value: ReactNode; note?: string; tone?: "accent" | "bad" }) {
  return (
    <div className={`tile${tone ? ` ${tone}` : ""}`}>
      <span className="k">{label}</span>
      <span className="v">{value}</span>
      {note && <span className="n">{note}</span>}
    </div>
  );
}

const TIER_TONE: Record<string, string> = {
  OBSERVE: "neutral", EXPLAIN: "neutral", SUGGEST: "accent",
  ACT_WITH_APPROVAL: "warn", AUTONOMOUS: "ok",
};

export function TierChip({ tier }: { tier: string }) {
  return <span className={`chip ${TIER_TONE[tier] ?? "neutral"}`}>{tier.replace(/_/g, " ")}</span>;
}

export function VerdictChip({ decision }: { decision: string }) {
  const tone = decision === "approve" ? "ok" : decision === "escalate" ? "warn" : "bad";
  return <span className={`chip ${tone}`}>{decision}</span>;
}

export function OutcomeChip({ outcome }: { outcome: string }) {
  const tone = outcome === "executed" ? "ok" : outcome === "held" ? "warn" : "bad";
  return <span className={`chip ${tone}`}>{outcome}</span>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty">{children}</p>;
}

export function Bar({ value }: { value: number }) {
  return (
    <div className="bar">
      <span style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
}

export function days(seconds: number): string {
  if (!seconds) return "0";
  const d = seconds / 86400;
  if (d >= 1) return `${d.toFixed(1)} d`;
  const h = seconds / 3600;
  if (h >= 1) return `${h.toFixed(1)} h`;
  return `${Math.round(seconds / 60)} min`;
}

export function shortHash(h: string): string {
  return h ? `${h.slice(0, 10)}…` : "—";
}

export function when(ts: string): string {
  try {
    return new Date(ts).toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return ts;
  }
}
