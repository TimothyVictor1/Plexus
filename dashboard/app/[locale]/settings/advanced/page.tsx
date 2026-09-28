"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { API_BASE, get } from "@/lib/api";

type Chain = { process_id: string; ok: boolean; entries: number; broken_at: number | null };
type Entry = {
  seq: number; id: string; process_id: string; entry_type: string;
  actor: { id: string; kind: string }; ts: string; hash: string; prev_hash: string;
};
type GraphNode = { key: string; kind: string; title: string };

/** The technical view. Everything here is deliberately kept out of the everyday screens;
 *  it exists so an engineer or an auditor can check the system's own record. */
export default function AdvancedPage() {
  const t = useTranslations("advanced");
  const locale = useLocale();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [chains, setChains] = useState<Chain[]>([]);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    get<{ entries: Entry[]; chains: Chain[] }>("/ledger?limit=40")
      .then((d) => { setEntries(d.entries); setChains(d.chains); })
      .catch((e) => setError(String(e.message)));
    get<{ nodes: GraphNode[] }>("/graph/nodes?limit=24")
      .then((d) => setNodes(d.nodes))
      .catch(() => setNodes([]));
  }, []);
  useEffect(load, [load]);

  const allOk = chains.every((c) => c.ok);

  return (
    <div className="page">
      <Link href={`/${locale}/settings`} className="small" style={{ fontWeight: 600 }}>
        ← {t("backToSettings")}
      </Link>

      <div className="page-head">
        <h1>{t("title")}</h1>
        <p>{t("sub")}</p>
      </div>

      {error && <section className="card"><p className="err">{error}</p></section>}

      <section className="card stack">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <h2>{t("ledger")}</h2>
          <span className={`chip ${allOk ? "good" : "slow"}`}>
            {allOk ? t("chainIntact") : t("chainBroken")}
          </span>
        </div>
        <p className="small muted">{t("ledgerBody")}</p>

        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr>
                {["seq", "type", "process", "actor", "when", "hash"].map((h) => (
                  <th key={h} style={{
                    textAlign: "left", padding: "6px 10px", color: "var(--muted)",
                    fontWeight: 500, borderBottom: "1px solid var(--line)",
                    fontSize: 12, textTransform: "uppercase", letterSpacing: ".08em",
                  }}>
                    {t(`column.${h}`)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id}>
                  <td style={{ padding: "6px 10px", fontFamily: "var(--mono)" }}>{e.seq}</td>
                  <td style={{ padding: "6px 10px" }}>{e.entry_type}</td>
                  <td style={{ padding: "6px 10px", fontFamily: "var(--mono)" }}>{e.process_id}</td>
                  <td style={{ padding: "6px 10px" }}>{e.actor?.id}</td>
                  <td style={{ padding: "6px 10px", fontFamily: "var(--mono)" }}>
                    {new Date(e.ts).toLocaleString("sv-SE", { dateStyle: "short", timeStyle: "short" })}
                  </td>
                  <td style={{
                    padding: "6px 10px", fontFamily: "var(--mono)", color: "var(--muted)",
                  }}>
                    {e.hash.slice(0, 10)}…
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {entries.length === 0 && <p className="muted">{t("noEntries")}</p>}
      </section>

      <section className="card stack">
        <h2>{t("graph")}</h2>
        <p className="small muted">{t("graphBody")}</p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {nodes.map((n) => (
            <span key={n.key} className="chip neutral" style={{ fontWeight: 500 }}>
              {n.kind}: {n.title.slice(0, 28)}
            </span>
          ))}
        </div>
        {nodes.length === 0 && <p className="muted">{t("noNodes")}</p>}
      </section>

      <section className="card stack">
        <h2>{t("api")}</h2>
        <p className="small muted">{t("apiBody")}</p>
        <a className="btn secondary" style={{ alignSelf: "flex-start" }}
           href={`${API_BASE}/v1/docs`} target="_blank" rel="noreferrer">
          {t("openApi")}
        </a>
      </section>
    </div>
  );
}
