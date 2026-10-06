"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import {
  get, post,
  type FinancialTwin, type GeneralTwin, type OrgModel, type PeopleTwin,
  type TwinAnswer, type TwinKind, type TwinLensOption,
} from "@/lib/api";
import { FinancialView, GeneralView, PeopleView, TwinTabs } from "@/components/TwinPicker";

type Kind = "person_leaves" | "demand_changes" | "process_changes";

const SEVERITY: Record<string, { chip: string; key: string }> = {
  stops: { chip: "slow", key: "stops" },
  slower: { chip: "watch", key: "slower" },
  fine: { chip: "good", key: "fine" },
};

export default function TwinPage() {
  const t = useTranslations("twin");
  const [model, setModel] = useState<OrgModel | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<Kind>("person_leaves");
  const [person, setPerson] = useState("");
  const [processId, setProcessId] = useState("");
  const [multiplier, setMultiplier] = useState(2);
  const [speedUp, setSpeedUp] = useState(50);
  const [result, setResult] = useState<TwinAnswer | null>(null);
  // Which reading to ask for. The operational one is the default, so the screen behaves
  // as it always did until someone chooses otherwise.
  const [lens, setLens] = useState("operations");
  const [lenses, setLenses] = useState<TwinLensOption[]>([]);
  // Which twin is being looked at. "operational" is the one that answers what-ifs, so it
  // stays the default and the screen behaves as it did before the others arrived.
  const [kinds, setKinds] = useState<TwinKind[]>([]);
  const [twinId, setTwinId] = useState("general");
  const [general, setGeneral] = useState<GeneralTwin | null>(null);
  const [financial, setFinancial] = useState<FinancialTwin | null>(null);
  const [peopleTwin, setPeopleTwin] = useState<PeopleTwin | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get<OrgModel>("/twin")
      .then((m) => {
        setModel(m);
        if (m.people[0]) setPerson(m.people[0].token);
        if (m.processes[0]) setProcessId(m.processes[0].id);
      })
      .catch((e) => setError(String(e.message)));
    get<TwinLensOption[]>("/twin/lenses").then(setLenses).catch(() => setLenses([]));
    get<TwinKind[]>("/twins").then(setKinds).catch(() => setKinds([]));
    get<GeneralTwin>("/twins/general").then(setGeneral).catch(() => setGeneral(null));
    get<FinancialTwin>("/twins/financial").then(setFinancial).catch(() => setFinancial(null));
    get<PeopleTwin>("/twins/people").then(setPeopleTwin).catch(() => setPeopleTwin(null));
  }, []);
  useEffect(load, [load]);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setResult(await post<TwinAnswer>("/twin/what-if", {
        kind,
        lens,
        person: kind === "person_leaves" ? person : null,
        process_id: kind === "person_leaves" ? null : processId,
        multiplier,
        speed_up_percent: kind === "process_changes" ? speedUp : 0,
      }));
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t("title")}</h1>
        <p>{t("sub")}</p>
      </div>

      {kinds.length > 0 && (
        <TwinTabs
          kinds={kinds}
          chosen={twinId}
          onChoose={setTwinId}
          unready={new Set((general?.cards ?? []).filter((c) => !c.readiness.ready).map((c) => c.id))}
        />
      )}

      {twinId === "general" && general && <GeneralView twin={general} onOpen={setTwinId} />}
      {twinId === "financial" && financial && <FinancialView twin={financial} />}
      {twinId === "people" && peopleTwin && <PeopleView twin={peopleTwin} />}
      {(twinId === "business" || twinId === "technical") && general && (
        <section className="card stack">
          <h2>{general.cards.find((c) => c.id === twinId)?.label}</h2>
          <div className="sunken stack" style={{ gap: 6 }}>
            <span style={{ lineHeight: 1.55 }}>
              {general.cards.find((c) => c.id === twinId)?.readiness.reason}
            </span>
            <span className="small muted">
              Connect: {general.cards.find((c) => c.id === twinId)?.readiness.needs.join(", ")}.
            </span>
          </div>
        </section>
      )}

      {error && <section className="card"><p className="err">{error}</p></section>}
      {!model && !error && <div className="skeleton" style={{ height: 260 }} />}

      {twinId === "operational" && model && (
        <>
          <section className="card stack">
            <h2>{t("askWhatIf")}</h2>
            <div className="row" style={{ alignItems: "flex-end", gap: 12 }}>
              <div className="stack" style={{ gap: 4, flex: "1 1 15rem", minWidth: 0 }}>
                <label className="small muted" htmlFor="kind">{t("question")}</label>
                <select id="kind" className="select" value={kind}
                        onChange={(e) => { setKind(e.target.value as Kind); setResult(null); }}>
                  <option value="person_leaves">{t("kind.person")}</option>
                  <option value="demand_changes">{t("kind.demand")}</option>
                  <option value="process_changes">{t("kind.process")}</option>
                </select>
              </div>

              {kind === "person_leaves" && (
                <div className="stack" style={{ gap: 4, flex: "1 1 12rem", minWidth: 0 }}>
                  <label className="small muted" htmlFor="who">{t("who")}</label>
                  <select id="who" className="select" value={person}
                          onChange={(e) => setPerson(e.target.value)}>
                    {model.people.map((p) => (
                      <option key={p.token} value={p.token}>
                        {p.label} · {t("stepsTouched", { n: p.roles.length })}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {kind !== "person_leaves" && (
                <div className="stack" style={{ gap: 4, flex: "1 1 14rem", minWidth: 0 }}>
                  <label className="small muted" htmlFor="what">{t("whichWork")}</label>
                  <select id="what" className="select" value={processId}
                          onChange={(e) => setProcessId(e.target.value)}>
                    {model.processes.map((p) => (
                      <option key={p.id} value={p.id}>{p.name}</option>
                    ))}
                  </select>
                </div>
              )}

              {kind === "demand_changes" && (
                <div className="stack" style={{ gap: 4, flex: "0 1 11rem" }}>
                  <label className="small muted" htmlFor="mult">
                    {t("howMuch", { n: multiplier })}
                  </label>
                  <input id="mult" type="range" min={0.5} max={5} step={0.5} value={multiplier}
                         style={{ accentColor: "var(--accent)" }}
                         onChange={(e) => setMultiplier(Number(e.target.value))} />
                </div>
              )}

              {kind === "process_changes" && (
                <div className="stack" style={{ gap: 4, flex: "0 1 11rem" }}>
                  <label className="small muted" htmlFor="speed">
                    {t("cutWait", { n: speedUp })}
                  </label>
                  <input id="speed" type="range" min={10} max={90} step={10} value={speedUp}
                         style={{ accentColor: "var(--accent)" }}
                         onChange={(e) => setSpeedUp(Number(e.target.value))} />
                </div>
              )}

              <button className="btn" disabled={busy} onClick={run}>
                {busy ? t("working") : t("run")}
              </button>
            </div>

            {lenses.length > 0 && (
              <div className="stack" style={{ gap: 8 }}>
                <span className="small muted" style={{ fontWeight: 700 }}>
                  {t("lensLabel")}
                </span>
                <div className="row" style={{ gap: 8 }}>
                  {lenses.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      className={`btn sm ${lens === option.id ? "" : "outline"}`}
                      aria-pressed={lens === option.id}
                      onClick={() => setLens(option.id)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                <span className="small muted">{lenses.find((o) => o.id === lens)?.blurb}</span>
              </div>
            )}
          </section>

          {result && (
            <section className="card stack">
              <h2>{result.scenario.title}</h2>
              <p style={{ fontSize: 16, lineHeight: 1.55 }}>{result.scenario.summary}</p>

              {result.scenario.effects.length > 0 && (
                <div className="stack" style={{ gap: 8 }}>
                  {result.scenario.effects.map((e, i) => (
                    <div key={i} className="sunken" style={{
                      display: "flex", gap: 12, alignItems: "flex-start",
                    }}>
                      <span className={`chip ${SEVERITY[e.severity].chip}`}>
                        {t(`severity.${SEVERITY[e.severity].key}`)}
                      </span>
                      <span style={{ flexGrow: 1, lineHeight: 1.5 }}>
                        {e.text}
                        {e.before && e.after && (
                          <span className="small muted">
                            {" "}({e.before.text} → {e.after.text})
                          </span>
                        )}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* The second reading. Always present, even when it is only to say that the
                  records cannot answer it — an empty panel that explains itself. */}
              {result.lens.id !== "operations" && (
                <div className="stack" style={{
                  gap: 10, padding: "16px 18px", borderRadius: "var(--radius-ctl)",
                  background: "var(--accent-deep)", border: "1px solid var(--accent-edge)",
                }}>
                  <span className="small" style={{ fontWeight: 700, color: "var(--hi)" }}>
                    {result.lens.label}
                  </span>

                  {result.lens.unavailable ? (
                    <p className="small muted" style={{ lineHeight: 1.55 }}>
                      {result.lens.unavailable}
                    </p>
                  ) : (
                    <>
                      <p style={{ fontSize: 15, lineHeight: 1.55 }}>{result.lens.summary}</p>
                      {result.lens.findings.map((f, i) => (
                        <div key={i} className="stack" style={{ gap: 2 }}>
                          <span style={{ fontWeight: 600 }}>{f.value}</span>
                          <span className="small muted">{f.label}</span>
                          {f.detail && (
                            <span className="small muted" style={{ lineHeight: 1.5 }}>
                              {f.detail}
                            </span>
                          )}
                        </div>
                      ))}
                    </>
                  )}
                </div>
              )}

              {result.scenario.cover.length > 0 && (
                <p className="small muted">
                  {t("couldCover", { people: result.scenario.cover.join(", ") })}
                </p>
              )}

              {result.scenario.assumptions.length > 0 && (
                <div className="stack" style={{ gap: 4 }}>
                  <span className="small muted" style={{ fontWeight: 700 }}>
                    {t("restsOn")}
                  </span>
                  <ul className="small muted" style={{
                    margin: 0, paddingLeft: 18, display: "flex",
                    flexDirection: "column", gap: 3,
                  }}>
                    {result.scenario.assumptions.map((a) => <li key={a}>{a}</li>)}
                  </ul>
                </div>
              )}
            </section>
          )}

          <div className="grid-2">
            <section className="card stack">
              <h2>{t("fragile")}</h2>
              <p className="small muted">{t("fragileBody")}</p>
              {model.risks.length === 0 && <p className="muted">{t("noRisks")}</p>}
              {model.risks.map((r, i) => (
                <div key={i} className="sunken" style={{ display: "flex", gap: 10 }}>
                  <span className={`chip ${r.kind === "single_point" ? "slow" : "watch"}`}>
                    {t(`risk.${r.kind}`)}
                  </span>
                  <span style={{ lineHeight: 1.5 }}>{r.text}</span>
                </div>
              ))}
            </section>

            <section className="card stack">
              <h2>{t("whoDoesWhat")}</h2>
              <p className="small muted">{t("pseudonyms")}</p>
              {model.people.slice(0, 8).map((p) => (
                <div key={p.token} className="sunken" style={{
                  display: "flex", justifyContent: "space-between", gap: 10,
                }}>
                  <span style={{ fontWeight: 600 }}>{p.label}</span>
                  <span className="small muted">
                    {t("acrossWork", { n: p.processes.length, events: p.events })}
                  </span>
                </div>
              ))}
            </section>
          </div>

          <p className="small muted">
            {t("basedOn", {
              days: model.window_days, events: model.total_events,
              people: model.people.length,
            })}
          </p>
        </>
      )}
    </div>
  );
}
