"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PageHeader from "@/components/PageHeader";
import { Bar, Empty, Panel, TierChip, days } from "@/components/ui";
import { TIERS, get, post, type ProcessDetail } from "@/lib/api";

export default function ProcessesPage() {
  const t = useTranslations("processes");
  const c = useTranslations("common");
  const [items, setItems] = useState<ProcessDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    get<{ processes: ProcessDetail[] }>("/processes")
      .then((d) => setItems(d.processes))
      .catch((e) => setError(String(e.message)));
  }, []);
  useEffect(load, [load]);

  async function move(id: string, direction: "promote" | "demote") {
    setBusy(id);
    try {
      await post("/processes/promote", { process_id: id, direction });
      load();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(null);
    }
  }

  async function pause(id: string, paused: boolean) {
    setBusy(id);
    try {
      await post("/pause", { paused, process_id: id });
      load();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader title={t("title")} sub={t("sub")} />
      <div className="content">
        {error && <Panel><p className="err">{error}</p></Panel>}
        {!items && !error && <Panel><Empty>{c("loading")}</Empty></Panel>}
        {items?.length === 0 && <Panel><Empty>{t("none")}</Empty></Panel>}

        {items?.map((p) => (
          <Panel
            key={p.id}
            title={
              <div className="inline">
                <h2>{p.name}</h2>
                <TierChip tier={p.tier} />
                {p.paused && <span className="chip bad">{t("paused")}</span>}
              </div>
            }
            actions={
              <>
                <button className="ghost sm" disabled={busy === p.id}
                        onClick={() => pause(p.id, !p.paused)}>
                  {p.paused ? t("resume") : t("pause")}
                </button>
                <button className="ghost sm" disabled={busy === p.id || p.tier === "OBSERVE"}
                        onClick={() => move(p.id, "demote")}>
                  {t("demote")}
                </button>
                <button className="sm" disabled={busy === p.id || p.tier === "AUTONOMOUS"}
                        onClick={() => move(p.id, "promote")}>
                  {t("promote")}
                </button>
              </>
            }
          >
            <p className="small muted" style={{ marginBottom: ".8rem" }}>{p.description}</p>

            <span className="eyebrow">{t("mined")}</span>
            <div className="flow" style={{ margin: ".4rem 0 1rem" }}>
              {p.steps.map((s, i) => (
                <div className="step" key={s.verb}>
                  <span className="so">{String(i + 1).padStart(2, "0")}</span>
                  <span className="sn">{s.name}</span>
                  <span className="sm">{s.frequency}× · {s.actors.length} {t("actors")}</span>
                </div>
              ))}
            </div>

            <div className="grid3">
              <div className="stack">
                <span className="eyebrow">{t("transitions")}</span>
                <div className="tablewrap">
                  <table>
                    <thead>
                      <tr><th>{t("from")}</th><th>{t("to")}</th><th className="mono">{t("count")}</th>
                          <th className="mono">{t("gap")}</th><th className="mono">{t("dependency")}</th></tr>
                    </thead>
                    <tbody>
                      {p.edges.map((e) => (
                        <tr key={`${e.source}-${e.target}`}>
                          <td className="mono">{e.source}</td>
                          <td className="mono">{e.target}</td>
                          <td className="num">{e.count}</td>
                          <td className="num">{days(e.median_gap_s)}</td>
                          <td className="num">{e.dependency.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <dl className="kv">
                  <dt>{t("cases")}</dt><dd className="mono">{p.case_count}</dd>
                  <dt>{t("cycle")}</dt>
                  <dd className="mono">{days(Number(p.metrics.median_cycle_time_s ?? 0))}</dd>
                  <dt>{t("variants")}</dt><dd className="mono">{String(p.metrics.variant_count ?? "—")}</dd>
                  <dt>{t("bottleneck")}</dt><dd className="mono">{String(p.metrics.bottleneck_step ?? "—")}</dd>
                </dl>
              </div>

              <div className="stack">
                <span className="eyebrow">{t("trust")}</span>
                <div className="inline" style={{ justifyContent: "space-between" }}>
                  <span className="mono" style={{ fontSize: "1.9rem", fontWeight: 700 }}>
                    {p.trust.trust.toFixed(2)}
                  </span>
                  <span className="small muted">{p.trust.samples} {t("decisions")}</span>
                </div>
                <Bar value={p.trust.trust} />
                <div className="tablewrap">
                  <table>
                    <tbody>
                      {Object.entries(p.trust.terms).map(([k, v]) => (
                        <tr key={k}>
                          <td className="mono small">{t(`term.${k}`)}</td>
                          <td className="num">{v >= 0 ? "+" : "−"}{Math.abs(v).toFixed(3)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="ladder">
                  {TIERS.map((tier) => {
                    const reached = TIERS.indexOf(tier) <= TIERS.indexOf(p.tier as never);
                    const req = tier === "OBSERVE"
                      ? t("startingRung")
                      : `${t("trust")} ${(p.thresholds[tier] ?? 0).toFixed(2)} · ${p.min_samples[tier] ?? 0} ${t("decisions")}`;
                    return (
                      <div key={tier} className="rung" data-on={reached ? "yes" : "no"}
                           data-cur={tier === p.tier ? "yes" : "no"}>
                        <span className="rn">{tier.replace(/_/g, " ")}</span>
                        <span className="rq">{req}</span>
                        <span className="rq">{tier === p.tier ? t("current") : reached ? t("cleared") : ""}</span>
                      </div>
                    );
                  })}
                </div>
                <p className="small muted">
                  {p.transition.eligible ? t("eligible", { tier: p.transition.to_tier }) : p.transition.reason}
                </p>
              </div>
            </div>
          </Panel>
        ))}
      </div>
    </>
  );
}
