"use client";

import { use, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import WaitTimeline from "@/components/WaitTimeline";
import { LEVEL_KEYS, get, type ProcessDetail } from "@/lib/api";

export default function ProcessPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const t = useTranslations("process");
  const health = useTranslations("health");
  const locale = useLocale();

  const [p, setP] = useState<ProcessDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showTech, setShowTech] = useState(false);

  const load = useCallback(() => {
    get<ProcessDetail>(`/processes/${id}`).then(setP).catch((e) => setError(String(e.message)));
  }, [id]);
  useEffect(load, [load]);

  if (error) {
    return <div className="page"><section className="card"><p className="err">{error}</p></section></div>;
  }
  if (!p) {
    return <div className="page"><div className="skeleton" style={{ height: 280 }} /></div>;
  }

  const a = p.autonomy;
  const atTop = a.level >= 5;
  const nextKey = LEVEL_KEYS[Math.min(a.level, 4)];
  const progress = a.needed > 0 ? Math.min(100, Math.round((a.decisions / a.needed) * 100)) : 100;

  return (
    <div className="page" style={{ gap: 18 }}>
      <Link href={`/${locale}/work`} className="small" style={{ fontWeight: 600, textDecoration: "none" }}>
        ← {t("allWork")}
      </Link>

      <div className="stack" style={{ gap: 8 }}>
        <div className="row" style={{ gap: 12 }}>
          <h1 style={{ fontSize: 32 }}>{p.name}</h1>
          <span className={`chip ${p.health}`}>{health(p.health)}</span>
          {p.paused && <span className="chip slow">{t("paused")}</span>}
        </div>
        <p className="muted">
          {p.description}. {t("happened", { n: p.case_count })} {t("seenIn", { tools: p.tools_text })}
        </p>
      </div>

      <section className="card" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
          <h2>{t("howItRuns")}</h2>
          <span className="small muted">{t("usuallyTakes", { time: p.total_duration.text })}</span>
        </div>

        <WaitTimeline steps={p.steps} waits={p.waits} />

        {p.help_tip && (
          <div style={{
            padding: "14px 16px", borderRadius: "var(--radius-ctl)",
            background: "var(--accent-deep)", display: "flex", flexDirection: "column", gap: 4,
          }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "var(--accent)" }}>
              {t("whereHelps")}
            </span>
            <span style={{ lineHeight: 1.5 }}>{p.help_tip}</span>
          </div>
        )}
      </section>

      <section className="card" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
        <div className="row" style={{ justifyContent: "space-between", alignItems: "baseline" }}>
          <h2>{t("howMuch")}</h2>
          {p.paused && <span className="small" style={{ color: "var(--slow)", fontWeight: 700 }}>{t("paused")}</span>}
        </div>

        <div className="grid-5" style={{ display: "grid", gridTemplateColumns: "repeat(5, minmax(0,1fr))", gap: 8 }}>
          {LEVEL_KEYS.map((key, i) => (
            <div key={key} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <span style={{
                height: 6, borderRadius: 3,
                background: i < a.level
                  ? (p.paused ? "var(--dim)" : "var(--accent)")
                  : "var(--line-2)",
              }} />
              <span style={{
                fontSize: 13,
                fontWeight: i === a.level - 1 ? 700 : 400,
                color: i === a.level - 1 ? "var(--text)" : "var(--muted)",
              }}>
                {t(`level.${key}`)}
              </span>
            </div>
          ))}
        </div>

        <p style={{ lineHeight: 1.5 }}>
          {p.paused ? t("pausedBody") : t(`levelBody.${LEVEL_KEYS[a.level - 1]}`)}
        </p>

        {!atTop && (
          <div className="stack" style={{ gap: 8 }}>
            <div className="row small muted" style={{ justifyContent: "space-between" }}>
              <span>
                {a.can_promote
                  ? t("readyTo", { what: t(`verb.${nextKey}`) })
                  : t("learningBefore", { what: t(`verb.${nextKey}`) })}
              </span>
              <span>{t("ofDecisions", { have: a.decisions, need: a.needed })}</span>
            </div>
            <div style={{ height: 5, borderRadius: 3, background: "var(--line)" }}>
              <div style={{
                height: 5, borderRadius: 3, background: "var(--accent)", width: `${progress}%`,
              }} />
            </div>
            {!a.can_promote && a.reason && <p className="small muted">{a.reason}</p>}
          </div>
        )}

        <div className="row">
          {!atTop && (
            <button className="btn" disabled={!a.can_promote} title={a.can_promote ? undefined : a.reason}>
              {t("letPlexus", { what: t(`verb.${nextKey}`) })}
            </button>
          )}
          <button className="btn outline">{p.paused ? t("resume") : t("pause")}</button>
          {a.level > 1 && <button className="btn quiet">{t("doLess")}</button>}
        </div>
        <p className="small muted">{t("controlsComing")}</p>
      </section>

      <button
        className="btn quiet"
        style={{ alignSelf: "flex-start", textDecoration: "underline", padding: 0 }}
        aria-expanded={showTech}
        onClick={() => setShowTech((v) => !v)}
      >
        {showTech ? t("hideTech") : t("showTech")}
      </button>

      {showTech && (
        <div style={{
          padding: "16px 18px", borderRadius: "var(--radius-ctl)", background: "#060607",
          fontFamily: "var(--mono)", fontSize: 13, lineHeight: 1.8, color: "#C8C8CE",
          overflowX: "auto",
        }}>
          <div>cases in event log: {p.technical.cases}</div>
          <div>variants: {p.technical.variants}</div>
          <div>bottleneck transition: {p.technical.bottleneck_transition || "none"}</div>
          <div>autonomy tier: {p.technical.tier} ({a.level} of 5), decisions {a.decisions}
            {!atTop ? ` / ${a.needed}` : ""}</div>
          <div>trust score: {p.technical.trust_score}</div>
          <div>trust components: {Object.entries(p.technical.trust_components)
            .map(([k, v]) => `${k}=${v}`).join("  ")}</div>
          <div style={{ marginTop: 8 }}>median gaps</div>
          {p.technical.median_gaps.map((g) => (
            <div key={`${g.from}-${g.to}`}>
              {"  "}{g.from} → {g.to}: {Math.round(g.seconds / 864) / 100} d,
              seen {g.count}×, dependency {g.dependency}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
