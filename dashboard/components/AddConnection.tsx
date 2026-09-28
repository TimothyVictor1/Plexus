"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import ConnectorIcon from "./ConnectorIcon";
import { get, post, type Catalogue, type ProviderOption } from "@/lib/api";

/** The add-a-connection panel: browse everything Plexus speaks to, see exactly what each one
 *  would read before agreeing, then connect it. */
export default function AddConnection({
  open, onClose, onConnected,
}: { open: boolean; onClose: () => void; onConnected: () => void }) {
  const t = useTranslations("connections");
  const [catalogue, setCatalogue] = useState<Catalogue[] | null>(null);
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<{ option: ProviderOption; group: Catalogue } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    get<Catalogue[]>("/connections/catalogue").then(setCatalogue).catch(() => setCatalogue([]));
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (open) panelRef.current?.focus();
    else { setChosen(null); setQuery(""); setError(null); }
  }, [open]);

  if (!open) return null;

  const needle = query.trim().toLowerCase();
  const groups = (catalogue ?? [])
    .map((g) => ({
      ...g,
      options: g.options.filter(
        (o) =>
          !needle ||
          o.name.toLowerCase().includes(needle) ||
          g.label.toLowerCase().includes(needle),
      ),
    }))
    .filter((g) => g.options.length > 0);

  async function connect(option: ProviderOption) {
    setBusy(true);
    setError(null);
    try {
      await post(`/connections/${option.category}/connect?provider=${option.key}`);
      onConnected();
      onClose();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={t("addTitle")}
      style={{
        position: "fixed", inset: 0, zIndex: 50, background: "rgba(4,4,5,.72)",
        display: "flex", alignItems: "center", justifyContent: "center", padding: 16,
      }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        style={{
          width: "min(720px, 100%)", maxHeight: "min(760px, 90dvh)", overflowY: "auto",
          background: "var(--panel)", border: "1px solid var(--line-2)",
          borderRadius: "var(--radius)", padding: 22,
          display: "flex", flexDirection: "column", gap: 16,
        }}
      >
        {chosen ? (
          <>
            <button className="btn quiet" style={{ alignSelf: "flex-start", padding: 0 }}
                    onClick={() => setChosen(null)}>
              ← {t("allTools")}
            </button>
            <div className="row" style={{ gap: 14, alignItems: "flex-start" }}>
              <ConnectorIcon category={chosen.group.category} size={52} />
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <h2 style={{ fontSize: 20 }}>{chosen.option.name}</h2>
                <span className="small muted">{chosen.group.label}</span>
              </div>
            </div>

            <div className="sunken stack" style={{ gap: 8 }}>
              <span style={{ fontWeight: 700, fontSize: 14 }}>{t("wouldRead")}</span>
              <ul className="small muted" style={{
                margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 4,
              }}>
                {chosen.option.reads.map((r) => <li key={r}>{r}</li>)}
              </ul>
              <span className="small muted" style={{ marginTop: 4 }}>
                {chosen.option.can_write ? t("canWriteLater") : t("readOnlyAlways")}
              </span>
            </div>

            {!chosen.option.available && (
              <p className="small" style={{ color: "var(--warn)", lineHeight: 1.5 }}>
                {t("needsSetup", { name: chosen.option.needs })}
              </p>
            )}
            {error && <p className="err">{error}</p>}

            <div className="row">
              <button className="btn" disabled={busy || !chosen.option.available}
                      onClick={() => connect(chosen.option)}>
                {t("connectNamed", { name: chosen.option.name })}
              </button>
              <button className="btn outline" onClick={onClose}>{t("cancel")}</button>
            </div>
          </>
        ) : (
          <>
            <div className="row" style={{ justifyContent: "space-between" }}>
              <h2 style={{ fontSize: 20 }}>{t("addTitle")}</h2>
              <button className="btn quiet" onClick={onClose} aria-label={t("cancel")}>✕</button>
            </div>
            <p className="small muted" style={{ lineHeight: 1.5 }}>{t("addBody")}</p>

            <div className="searchbar" style={{ padding: "6px 6px 6px 16px" }}>
              <label htmlFor="toolSearch" className="sr-only">{t("search")}</label>
              <input id="toolSearch" className="input" value={query} placeholder={t("search")}
                     style={{ fontSize: 15 }} onChange={(e) => setQuery(e.target.value)} />
            </div>

            {!catalogue && <div className="skeleton" style={{ height: 200 }} />}
            {catalogue && groups.length === 0 && <p className="muted">{t("noMatch")}</p>}

            {groups.map((group) => (
              <div key={group.category} className="stack" style={{ gap: 8 }}>
                <span className="small muted" style={{ fontWeight: 700 }}>
                  {group.label} · {group.blurb}
                </span>
                {group.options.map((option) => (
                  <button
                    key={option.key}
                    onClick={() => setChosen({ option, group })}
                    style={{
                      display: "flex", alignItems: "center", gap: 12, padding: "10px 12px",
                      background: "var(--card)", border: "1px solid var(--line)",
                      borderRadius: "var(--radius-ctl)", textAlign: "left",
                      color: "var(--text)", width: "100%",
                    }}
                  >
                    <ConnectorIcon category={group.category} size={36} />
                    <span style={{ display: "flex", flexDirection: "column", gap: 2, flexGrow: 1 }}>
                      <span style={{ fontWeight: 600 }}>{option.name}</span>
                      <span className="small muted">
                        {option.available ? t("readyToConnect") : t("setupNeeded")}
                      </span>
                    </span>
                    <span className="small" style={{ color: "var(--accent)" }}>→</span>
                  </button>
                ))}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
