"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PageHeader from "@/components/PageHeader";
import { Empty, Panel, Tile, TierChip } from "@/components/ui";
import { get, post, type Overview } from "@/lib/api";

export default function OverviewPage() {
  const t = useTranslations("overview");
  const c = useTranslations("common");
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get<Overview>("/overview").then(setData).catch((e) => setError(String(e.message)));
  }, []);
  useEffect(load, [load]);

  async function togglePause() {
    if (!data) return;
    setBusy(true);
    try {
      await post("/pause", { paused: !data.tenant.paused });
      load();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  if (error) {
    return (
      <>
        <PageHeader title={t("title")} />
        <div className="content">
          <Panel title={c("apiUnreachable")}>
            <p className="err">{error}</p>
            <p className="small muted" style={{ marginTop: ".5rem" }}>{c("apiHint")}</p>
          </Panel>
        </div>
      </>
    );
  }
  if (!data) {
    return (
      <>
        <PageHeader title={t("title")} />
        <div className="content"><Panel><Empty>{c("loading")}</Empty></Panel></div>
      </>
    );
  }

  return (
    <>
      <PageHeader
        title={t("title")}
        sub={t("sub")}
        actions={
          <button className={data.tenant.paused ? "" : "danger"} onClick={togglePause} disabled={busy}>
            {data.tenant.paused ? t("resume") : t("killSwitch")}
          </button>
        }
      />
      <div className="content">
        {data.tenant.paused && (
          <Panel title={t("pausedTitle")}>
            <p className="small">{t("pausedBody")}</p>
          </Panel>
        )}

        <div className="tiles">
          <Tile label={t("documents")} value={data.documents}
                note={Object.entries(data.documents_by_kind).map(([k, v]) => `${v} ${k}`).join(" · ")} />
          <Tile label={t("events")} value={data.events} note={t("eventsNote")} />
          <Tile label={t("graphNodes")} value={data.graph_nodes}
                note={Object.entries(data.graph).map(([k, v]) => `${v} ${k}`).join(" · ")} />
          <Tile label={t("vault")} value={data.vault_entries} note={t("vaultNote")} tone="accent" />
          <Tile label={t("writes")} value={data.adapter_writes} note={t("writesNote")} />
          <Tile
            label={t("chain")}
            value={data.chain_ok ? t("intact") : t("broken")}
            note={`${data.chains.reduce((n, ch) => n + ch.entries, 0)} ${t("entries")}`}
            tone={data.chain_ok ? undefined : "bad"}
          />
        </div>

        <Panel title={t("processesTitle")} flush>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>{t("process")}</th>
                  <th>{t("tier")}</th>
                  <th className="mono">{t("cases")}</th>
                  <th className="mono">{t("steps")}</th>
                  <th className="mono">{t("cycle")}</th>
                  <th>{t("bottleneck")}</th>
                </tr>
              </thead>
              <tbody>
                {data.processes.map((p) => (
                  <tr key={p.id}>
                    <td><strong>{p.name}</strong><br /><span className="small muted mono">{p.id}</span></td>
                    <td><TierChip tier={p.tier} />{p.paused && <> <span className="chip bad">{t("paused")}</span></>}</td>
                    <td className="num">{p.case_count}</td>
                    <td className="num">{String(p.metrics.step_count ?? "—")}</td>
                    <td className="num">
                      {Number(p.metrics.median_cycle_time_s ?? 0) > 0
                        ? `${(Number(p.metrics.median_cycle_time_s) / 86400).toFixed(1)} d`
                        : "—"}
                    </td>
                    <td className="mono small">{String(p.metrics.bottleneck_step ?? "—")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <div className="grid2">
          <Panel title={t("modelTitle")}>
            <dl className="kv">
              <dt>{t("calls")}</dt><dd className="mono">{data.model_calls.count}</dd>
              <dt>{t("cost")}</dt><dd className="mono">${data.model_calls.cost_usd.toFixed(4)}</dd>
              <dt>{t("latency")}</dt><dd className="mono">{data.model_calls.avg_latency_ms} ms</dd>
            </dl>
            <p className="small muted" style={{ marginTop: ".7rem" }}>{t("modelNote")}</p>
          </Panel>
          <Panel title={t("chainTitle")}>
            <div className="stack">
              {data.chains.length === 0 && <span className="small muted">{t("noChain")}</span>}
              {data.chains.map((ch) => (
                <div key={ch.process_id} className="inline" style={{ justifyContent: "space-between" }}>
                  <span className="mono small">{ch.process_id}</span>
                  <span className="inline">
                    <span className="mono small muted">{ch.entries} {t("entries")}</span>
                    <span className={`chip ${ch.ok ? "ok" : "bad"}`}>
                      {ch.ok ? t("intact") : `${t("broken")} @${ch.broken_at}`}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </>
  );
}
