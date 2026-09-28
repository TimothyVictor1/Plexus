"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import AddConnection from "@/components/AddConnection";
import ConnectorIcon from "@/components/ConnectorIcon";
import { get, post, signalRefresh, type ConnectionsView, type ConnectorInfo } from "@/lib/api";

export default function ConnectionsPage() {
  const t = useTranslations("connections");
  const [view, setView] = useState<ConnectionsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const load = useCallback(() => {
    get<ConnectionsView>("/connections").then(setView).catch((e) => setError(String(e.message)));
  }, []);
  useEffect(load, [load]);

  async function disconnect(tool: ConnectorInfo) {
    setBusy(tool.category);
    setError(null);
    try {
      await post(`/connections/${tool.category}/disconnect`);
      load();
      signalRefresh();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(null);
    }
  }

  const connected = view?.connections.filter((c) => c.status === "connected") ?? [];
  const available = view?.connections.filter((c) => c.status !== "connected") ?? [];

  return (
    <div className="page">
      <div className="page-head">
        <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
          <div className="stack" style={{ gap: 6 }}>
            <h1>{t("title")}</h1>
            <p className="muted">
              {t("sub")}{" "}
              {view && t("countOf", { n: view.connected_count, total: view.total })}
            </p>
          </div>
          <button className="btn" onClick={() => setAdding(true)}>+ {t("add")}</button>
        </div>
      </div>

      {error && <section className="card"><p className="err">{error}</p></section>}
      {!view && !error && <div className="skeleton" style={{ height: 240 }} />}

      {view && (
        <>
          {connected.length > 0 && (
            <div className="stack" style={{ gap: 10 }}>
              <h2 className="small muted" style={{ fontWeight: 700 }}>
                {t("connectedHeading", { n: connected.length })}
              </h2>
              <div className="grid-2">
                {connected.map((tool) => (
                  <div key={tool.category} className="card" style={{
                    display: "flex", alignItems: "center", gap: 14, padding: 16,
                    border: "1px solid var(--accent-edge)",
                  }}>
                    <ConnectorIcon category={tool.category} />
                    <div style={{ display: "flex", flexDirection: "column", gap: 2, flexGrow: 1 }}>
                      <span style={{ fontWeight: 700 }}>{tool.label}</span>
                      <span className="small muted">
                        {tool.document_count > 0
                          ? t("readingFrom", { n: tool.document_count })
                          : t("nothingYet")}
                      </span>
                    </div>
                    <button className="btn outline sm" disabled={busy === tool.category}
                            onClick={() => disconnect(tool)}>
                      {t("disconnectShort")}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {available.length > 0 && (
            <div className="stack" style={{ gap: 10 }}>
              <h2 className="small muted" style={{ fontWeight: 700 }}>{t("availableHeading")}</h2>
              <div className="grid-4">
                {available.map((tool) => (
                  <button key={tool.category} className="card" onClick={() => setAdding(true)}
                          style={{
                            display: "flex", flexDirection: "column", gap: 10, padding: 16,
                            border: "1px solid var(--raised-2)", textAlign: "left",
                            color: "var(--text)",
                          }}>
                    <ConnectorIcon category={tool.category} size={36} />
                    <span style={{ fontWeight: 600 }}>{tool.label}</span>
                    <span className="small muted">{tool.examples}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <section className="card grid-3" style={{ gap: 20 }}>
            {view.privacy.map((fact) => (
              <div key={fact.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span style={{ fontSize: 15, fontWeight: 700 }}>
                  {fact.key === "residency" && fact.ok !== "true"
                    ? t("privacy.residencyOffTitle")
                    : t(`privacy.${fact.key}Title`)}
                </span>
                <span className="small muted" style={{ lineHeight: 1.5 }}>
                  {fact.key === "residency" && fact.ok !== "true"
                    ? t("privacy.residencyOffBody", { region: fact.region })
                    : t(`privacy.${fact.key}Body`)}
                </span>
              </div>
            ))}
          </section>
        </>
      )}

      <AddConnection open={adding} onClose={() => setAdding(false)}
                     onConnected={() => { load(); signalRefresh(); }} />
    </div>
  );
}
