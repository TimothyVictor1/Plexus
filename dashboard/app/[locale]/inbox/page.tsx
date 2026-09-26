"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PageHeader from "@/components/PageHeader";
import { Empty, OutcomeChip, Panel, VerdictChip } from "@/components/ui";
import {
  TIERS, get, post,
  type InboxItem, type Outcome, type RunResult,
} from "@/lib/api";

const SCENARIOS = [
  { id: "proc-quote", key: "task" },
  { id: "proc-quote-invoice", key: "invoice" },
  { id: "proc-export", key: "export" },
];

export default function InboxPage() {
  const t = useTranslations("inbox");
  const c = useTranslations("common");
  const [items, setItems] = useState<InboxItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scenario, setScenario] = useState(SCENARIOS[0].id);
  const [tier, setTier] = useState<string>("ACT_WITH_APPROVAL");
  const [run, setRun] = useState<RunResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [decided, setDecided] = useState<Record<string, Outcome>>({});

  const load = useCallback(() => {
    get<{ items: InboxItem[] }>("/inbox")
      .then((d) => setItems(d.items))
      .catch((e) => setError(String(e.message)));
  }, []);
  useEffect(load, [load]);

  async function runPipeline() {
    setBusy(true); setError(null);
    try {
      setRun(await post<RunResult>("/actions/run", { process_id: scenario, tier }));
      load();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  async function decide(id: string, decision: "approve" | "reject") {
    setBusy(true); setError(null);
    try {
      const out = await post<Outcome>(`/inbox/${id}/decide`, { decision });
      setDecided((d) => ({ ...d, [id]: out }));
      load();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <PageHeader title={t("title")} sub={t("sub")} />
      <div className="content">
        <Panel title={t("runTitle")}>
          <p className="small muted" style={{ marginBottom: ".8rem" }}>{t("runBody")}</p>
          <div className="row">
            <div className="field">
              <label className="fl" htmlFor="scenario">{t("trigger")}</label>
              <select id="scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
                {SCENARIOS.map((s) => (
                  <option key={s.id} value={s.id}>{t(`scenario.${s.key}`)}</option>
                ))}
              </select>
            </div>
            <div className="field">
              <label className="fl" htmlFor="tier">{t("tier")}</label>
              <select id="tier" value={tier} onChange={(e) => setTier(e.target.value)}>
                {TIERS.map((x) => <option key={x} value={x}>{x.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div className="field" style={{ flex: "0 0 auto" }}>
              <button onClick={runPipeline} disabled={busy}>{t("run")}</button>
            </div>
          </div>

          {error && <p className="err" style={{ marginTop: ".7rem" }}>{error}</p>}

          {run && (
            <div className="stack" style={{ marginTop: "1rem" }}>
              <div className="inline">
                <span className="eyebrow">{t("result")}</span>
                <VerdictChip decision={run.verdict.decision} />
                <OutcomeChip outcome={run.outcome.outcome} />
                <span className="chip neutral">{run.tier.replace(/_/g, " ")}</span>
              </div>
              <div className="grid2">
                <div className="stack">
                  <span className="eyebrow">{t("proposal")}</span>
                  <dl className="kv">
                    <dt>{t("operation")}</dt><dd className="mono">{run.action.operation}</dd>
                    <dt>{t("risk")}</dt><dd>{run.action.risk_class}</dd>
                    <dt>{t("actorModel")}</dt>
                    <dd className="mono">{run.action.actor_model.vendor}/{run.action.actor_model.model}</dd>
                    <dt>{t("cited")}</dt><dd>{run.action.cited_context?.length ?? 0}</dd>
                  </dl>
                  <div className="code">{JSON.stringify(run.action.arguments, null, 2)}</div>
                </div>
                <div className="stack">
                  <span className="eyebrow">{t("simulation")}</span>
                  <p className="small">{run.simulation.summary}</p>
                  <dl className="kv">
                    <dt>{t("changes")}</dt><dd>{run.simulation.changes.length}</dd>
                    <dt>{t("blast")}</dt>
                    <dd className="mono">{run.simulation.blast_radius.normalised.toFixed(2)}</dd>
                  </dl>
                  {run.simulation.violations.length > 0 && (
                    <div className="stack">
                      {run.simulation.violations.map((v) => (
                        <div key={v.rule_id} className="inline">
                          <span className={`chip ${v.effect === "block" ? "bad" : "warn"}`}>{v.rule_id}</span>
                          <span className="small">{v.rule_name}</span>
                        </div>
                      ))}
                    </div>
                  )}
                  <span className="eyebrow">{t("verdict")}</span>
                  <p className="small mono muted">
                    {run.verdict.verifier_model.vendor}/{run.verdict.verifier_model.model}
                  </p>
                  <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem" }}>
                    {run.verdict.reasons.map((r, i) => <li key={i}>{r.text}</li>)}
                  </ul>
                </div>
              </div>
              <div className={`panel`} style={{ background: "var(--panel-2)" }}>
                <div className="body">
                  <strong>{run.outcome.title}</strong>
                  <p className="small" style={{ marginTop: ".3rem" }}>{run.outcome.detail}</p>
                  {run.outcome.write_result?.message && (
                    <p className="small mono muted" style={{ marginTop: ".3rem" }}>
                      {run.outcome.write_result.message}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}
        </Panel>

        <Panel title={t("pendingTitle")}>
          {!items && <Empty>{c("loading")}</Empty>}
          {items?.length === 0 && <Empty>{t("empty")}</Empty>}
          <div className="stack">
            {items?.map((item) => (
              <article key={item.id} className="panel" style={{ background: "var(--panel-2)" }}>
                <header>
                  <div className="inline">
                    <span className="mono" style={{ fontWeight: 600 }}>{item.operation}</span>
                    <span className="chip neutral">{item.risk_class}</span>
                    {item.verdict && <VerdictChip decision={item.verdict.decision} />}
                  </div>
                  <div className="inline">
                    <button className="ghost sm" disabled={busy}
                            onClick={() => decide(item.id, "reject")}>{t("reject")}</button>
                    <button className="sm" disabled={busy || !item.verdict}
                            onClick={() => decide(item.id, "approve")}>{t("approve")}</button>
                  </div>
                </header>
                <div className="body">
                  <p className="small">{item.rationale}</p>
                  <div className="grid2" style={{ marginTop: ".7rem" }}>
                    <dl className="kv">
                      <dt>{t("process")}</dt><dd className="mono">{item.process_id}</dd>
                      <dt>{t("cited")}</dt>
                      <dd className="mono small">
                        {item.cited_context?.map((cc) => cc.key).join(", ") || "—"}
                      </dd>
                      <dt>{t("blast")}</dt>
                      <dd className="mono">
                        {item.simulation?.blast_radius.normalised.toFixed(2) ?? "—"}
                      </dd>
                    </dl>
                    <div className="stack">
                      {item.simulation?.violations.map((v) => (
                        <div key={v.rule_id} className="inline">
                          <span className={`chip ${v.effect === "block" ? "bad" : "warn"}`}>{v.rule_id}</span>
                          <span className="small">{v.evidence}</span>
                        </div>
                      ))}
                      {item.verdict?.reasons.slice(0, 2).map((r, i) => (
                        <p key={i} className="small muted">{r.text}</p>
                      ))}
                    </div>
                  </div>
                  {decided[item.id] && (
                    <p className="small" style={{ marginTop: ".6rem" }}>
                      <OutcomeChip outcome={decided[item.id].outcome} />{" "}
                      <strong>{decided[item.id].title}</strong> {decided[item.id].detail}
                    </p>
                  )}
                </div>
              </article>
            ))}
          </div>
        </Panel>
      </div>
    </>
  );
}
