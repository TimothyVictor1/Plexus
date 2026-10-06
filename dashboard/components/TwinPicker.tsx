"use client";

import type { FinancialTwin, GeneralTwin, PeopleTwin, TwinKind } from "@/lib/api";

/** The twins a company can look at, chosen from one row.
 *
 *  A twin that cannot be built from what this company has connected still appears, and says
 *  what is missing. Hiding it would leave a person wondering whether Plexus can do the thing
 *  at all; showing it empty would read as a fault. Naming what to connect is the only version
 *  that is both honest and useful.
 */
export function TwinTabs({
  kinds, chosen, onChoose, unready,
}: {
  kinds: TwinKind[];
  chosen: string;
  onChoose: (id: string) => void;
  unready: Set<string>;
}) {
  return (
    <div className="row" style={{ gap: 8 }}>
      {kinds.map((k) => (
        <button
          key={k.id}
          type="button"
          className={`btn sm ${chosen === k.id ? "" : "outline"}`}
          aria-pressed={chosen === k.id}
          onClick={() => onChoose(k.id)}
          title={k.blurb}
          style={unready.has(k.id) ? { opacity: 0.55 } : undefined}
        >
          {k.label}
        </button>
      ))}
    </div>
  );
}

function NotReady({ card }: { card: { readiness: { reason: string; needs: string[] } } }) {
  return (
    <div className="sunken stack" style={{ gap: 6 }}>
      <span style={{ lineHeight: 1.55 }}>{card.readiness.reason}</span>
      {card.readiness.needs.length > 0 && (
        <span className="small muted">Connect: {card.readiness.needs.join(", ")}.</span>
      )}
    </div>
  );
}

export function GeneralView({ twin, onOpen }: { twin: GeneralTwin; onOpen: (id: string) => void }) {
  return (
    <section className="card stack">
      <h2>The whole company</h2>
      <p style={{ fontSize: 16, lineHeight: 1.55 }}>{twin.summary}</p>
      <div className="grid-2">
        {twin.cards.map((card) => (
          <button
            key={card.id}
            type="button"
            className="sunken stack"
            onClick={() => card.readiness.ready && onOpen(card.id)}
            disabled={!card.readiness.ready}
            style={{
              gap: 6, textAlign: "left", border: "1px solid var(--line-2)",
              cursor: card.readiness.ready ? "pointer" : "default",
              opacity: card.readiness.ready ? 1 : 0.7,
            }}
          >
            <span style={{ fontWeight: 700 }}>{card.label}</span>
            <span className="small muted" style={{ lineHeight: 1.5 }}>
              {card.readiness.ready ? card.headline : card.readiness.reason}
            </span>
            {card.figures.length > 0 && (
              <span className="row" style={{ gap: 6 }}>
                {card.figures.map((f) => (
                  <span key={f} className="chip neutral">{f}</span>
                ))}
              </span>
            )}
          </button>
        ))}
      </div>
    </section>
  );
}

export function FinancialView({ twin }: { twin: FinancialTwin }) {
  if (!twin.ready) return <section className="card stack"><h2>Where money sits</h2><NotReady card={{ readiness: { reason: twin.reason, needs: ["a tool that holds invoices or expenses"] } }} /></section>;
  return (
    <section className="card stack">
      <h2>Where money sits</h2>
      <p style={{ fontSize: 16, lineHeight: 1.55 }}>{twin.summary}</p>
      {twin.at_rest.map((m) => (
        <div key={m.process_id} className="sunken stack" style={{ gap: 4 }}>
          <span style={{ fontWeight: 700 }}>
            {m.total.toLocaleString()} {m.currency}
          </span>
          <span className="small">{m.process_name}</span>
          <span className="small muted" style={{ lineHeight: 1.5 }}>{m.note}</span>
        </div>
      ))}
    </section>
  );
}

export function PeopleView({ twin }: { twin: PeopleTwin }) {
  return (
    <section className="card stack">
      <h2>Who knows what</h2>
      <p style={{ fontSize: 16, lineHeight: 1.55 }}>{twin.summary}</p>
      {twin.people.map((person) => (
        <div key={person.token} className="sunken stack" style={{ gap: 6 }}>
          <span style={{ fontWeight: 700 }}>{person.label}</span>
          <span className="small muted" style={{ lineHeight: 1.5 }}>{person.summary}</span>
          {person.handover.length > 0 && (
            <div className="stack" style={{ gap: 4 }}>
              <span className="small" style={{ fontWeight: 600 }}>If they left</span>
              {person.handover.slice(0, 4).map((h, i) => (
                <span key={i} className="row" style={{ gap: 8, alignItems: "flex-start" }}>
                  <span className={`chip ${h.urgency === "only_them" ? "slow" : "watch"}`}>
                    {h.urgency === "only_them" ? "Only them" : "Mostly them"}
                  </span>
                  <span className="small muted" style={{ flexGrow: 1, lineHeight: 1.5 }}>
                    {h.note}
                  </span>
                </span>
              ))}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
