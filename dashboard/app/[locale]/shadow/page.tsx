"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";

import { get, type Scorecard, type Scoreboard, type ShadowRun } from "@/lib/api";

/** What each agent has earned so far by watching.
 *
 *  The screen's job is to make a track record checkable rather than impressive. Every number
 *  opens into the individual predictions behind it, because a scoreboard nobody can audit is
 *  just a claim with a percentage on it.
 */
export default function ShadowPage() {
  const t = useTranslations("shadow");
  const [board, setBoard] = useState<Scoreboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [runs, setRuns] = useState<Record<string, ShadowRun[]>>({});

  const load = useCallback(() => {
    get<Scoreboard>("/shadow")
      .then(setBoard)
      .catch((e) => setError(String(e.message)));
  }, []);
  useEffect(load, [load]);

  async function toggle(card: Scorecard) {
    if (open === card.process_id) {
      setOpen(null);
      return;
    }
    setOpen(card.process_id);
    if (!runs[card.process_id]) {
      try {
        setRuns((r) => ({ ...r, [card.process_id]: [] }));
        const got = await get<ShadowRun[]>(`/shadow/${card.process_id}`);
        setRuns((r) => ({ ...r, [card.process_id]: got }));
      } catch {
        /* the scorecard still stands on its own */
      }
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t("title")}</h1>
        <p>{t("sub")}</p>
      </div>

      {error && <section className="card"><p className="err">{error}</p></section>}
      {!board && !error && <div className="skeleton" style={{ height: 220 }} />}

      {board && (
        <>
          <section className="card stack">
            <p style={{ fontSize: 16, lineHeight: 1.55 }}>{board.summary}</p>
          </section>

          {board.cards.length === 0 && (
            <section className="card stack">
              <p className="muted">{t("nobody")}</p>
            </section>
          )}

          {board.cards.map((card) => (
            <section key={`${card.process_id}-${card.agent}`} className="card stack">
              <div className="row" style={{ justifyContent: "space-between" }}>
                <h2>{card.process_name}</h2>
                <span className={`chip ${card.ready ? "smooth" : "neutral"}`}>
                  {card.ready ? t("ready") : t("watching")}
                </span>
              </div>

              <p style={{ lineHeight: 1.55 }}>{card.verdict_text}</p>

              {card.settled > 0 && (
                <div className="grid-3">
                  <div className="sunken stack" style={{ gap: 2 }}>
                    <span style={{ fontSize: 22, fontWeight: 700 }}>{card.agreed}</span>
                    <span className="small muted">{t("agreed")}</span>
                  </div>
                  <div className="sunken stack" style={{ gap: 2 }}>
                    <span style={{ fontSize: 22, fontWeight: 700 }}>{card.edited}</span>
                    <span className="small muted">{t("edited")}</span>
                  </div>
                  <div className="sunken stack" style={{ gap: 2 }}>
                    <span style={{ fontSize: 22, fontWeight: 700 }}>{card.rejected}</span>
                    <span className="small muted">{t("rejected")}</span>
                  </div>
                </div>
              )}

              <button className="btn outline sm" style={{ alignSelf: "flex-start" }}
                      onClick={() => toggle(card)}>
                {open === card.process_id ? t("hideRuns") : t("showRuns")}
              </button>

              {open === card.process_id && (
                <div className="stack" style={{ gap: 8 }}>
                  {(runs[card.process_id] ?? []).length === 0 && (
                    <p className="small muted">{t("nothingYet")}</p>
                  )}
                  {(runs[card.process_id] ?? []).map((run) => (
                    <div key={run.id} className="sunken stack" style={{ gap: 4 }}>
                      <span className="row" style={{ gap: 8 }}>
                        <span className={`chip ${
                          run.verdict === "agreed" ? "smooth"
                          : run.verdict === "rejected" ? "slow"
                          : run.verdict === "edited" ? "watch" : "neutral"
                        }`}>
                          {run.verdict === "pending" ? t("pending") : run.verdict}
                        </span>
                        <span className="small muted">
                          {new Date(run.predicted_at).toLocaleDateString()}
                        </span>
                      </span>
                      <span className="small">
                        <strong>{t("predicted")}:</strong>{" "}
                        {String(run.predicted.title ?? run.predicted.operation ?? "—")}
                      </span>
                      {run.note && <span className="small muted">{run.note}</span>}
                    </div>
                  ))}
                </div>
              )}
            </section>
          ))}

          <section className="card stack">
            <h2>{t("howItWorks")}</h2>
            <p className="small muted" style={{ lineHeight: 1.6 }}>{t("howItWorksBody")}</p>
          </section>
        </>
      )}
    </div>
  );
}
