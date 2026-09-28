"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { get, post, signalRefresh, type ConnectionsView, type ConnectorInfo } from "@/lib/api";

export default function ConnectionsPage() {
  const t = useTranslations("connections");
  const [view, setView] = useState<ConnectionsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(() => {
    get<ConnectionsView>("/connections").then(setView).catch((e) => setError(String(e.message)));
  }, []);
  useEffect(load, [load]);

  async function toggle(tool: ConnectorInfo) {
    const action = tool.status === "connected" ? "disconnect" : "connect";
    setBusy(tool.category);
    setError(null);
    try {
      await post(`/connections/${tool.category}/${action}`);
      load();
      signalRefresh();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t("title")}</h1>
        <p>
          {t("sub")}{" "}
          {view && t("countOf", { n: view.connected_count, total: view.total })}
        </p>
      </div>

      {error && <section className="card"><p className="err">{error}</p></section>}
      {!view && !error && <div className="skeleton" style={{ height: 240 }} />}

      {view && (
        <>
          <div className="grid-4">
            {view.connections.map((tool) => {
              const connected = tool.status === "connected";
              const unavailable = tool.status === "not_configured";
              return (
                <div
                  key={tool.category}
                  className="card"
                  style={{
                    padding: 18, display: "flex", flexDirection: "column", gap: 14,
                    border: `1px solid ${connected ? "var(--accent-edge)" : "var(--raised-2)"}`,
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                    <span style={{ fontSize: 15, fontWeight: 700 }}>{tool.label}</span>
                    <span className="small muted">{tool.examples}</span>
                  </div>

                  {connected && tool.document_count > 0 && (
                    <span className="small muted">
                      {t("readingFrom", { n: tool.document_count })}
                    </span>
                  )}
                  {unavailable && <span className="small muted">{t("notAvailable")}</span>}

                  <button
                    className={connected ? "btn outline sm" : "btn sm"}
                    style={{ minHeight: 40, width: "100%" }}
                    disabled={busy === tool.category || unavailable}
                    title={unavailable ? tool.detail : undefined}
                    onClick={() => toggle(tool)}
                  >
                    {unavailable
                      ? t("unavailable")
                      : connected
                        ? t("disconnect")
                        : t("connect")}
                  </button>
                </div>
              );
            })}
          </div>

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
    </div>
  );
}
