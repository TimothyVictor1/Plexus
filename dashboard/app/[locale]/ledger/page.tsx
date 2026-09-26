"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PageHeader from "@/components/PageHeader";
import { Empty, Panel, shortHash, when } from "@/components/ui";
import { currentRole, get, post, type LedgerEntry } from "@/lib/api";

type Chain = { process_id: string; ok: boolean; entries: number; broken_at: number | null; detail?: string };

const TONE: Record<string, string> = {
  execution: "ok", approval: "ok", promotion: "ok", unpause: "ok",
  suggestion: "warn", shadow_run: "neutral", pause: "warn",
  rejection: "bad", reversal: "bad", demotion: "bad", refusal: "bad",
};

export default function LedgerPage() {
  const t = useTranslations("ledger");
  const c = useTranslations("common");
  const [entries, setEntries] = useState<LedgerEntry[] | null>(null);
  const [chains, setChains] = useState<Chain[]>([]);
  const [filter, setFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    const q = filter ? `?entry_type=${encodeURIComponent(filter)}` : "";
    get<{ entries: LedgerEntry[]; chains: Chain[] }>(`/ledger${q}`)
      .then((d) => { setEntries(d.entries); setChains(d.chains); })
      .catch((e) => setError(String(e.message)));
  }, [filter]);
  useEffect(load, [load]);

  async function tamper() {
    setBusy(true); setError(null);
    try {
      await post("/ledger/tamper");
      load();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  const allOk = chains.every((ch) => ch.ok);
  const types = ["", "execution", "approval", "rejection", "suggestion", "shadow_run",
                 "reversal", "refusal", "promotion", "demotion", "pause", "unpause"];

  return (
    <>
      <PageHeader
        title={t("title")} sub={t("sub")}
        actions={
          <button className="ghost" onClick={tamper} disabled={busy || currentRole() !== "admin"}
                  title={currentRole() !== "admin" ? t("adminOnly") : undefined}>
            {t("tamper")}
          </button>
        }
      />
      <div className="content">
        <Panel title={t("chainTitle")}>
          <div className="stack">
            {chains.length === 0 && <span className="small muted">{t("noChain")}</span>}
            {chains.map((ch) => (
              <div key={ch.process_id} className="inline" style={{ justifyContent: "space-between" }}>
                <span className="mono small">{ch.process_id}</span>
                <span className="inline">
                  <span className="small muted mono">{ch.entries} {t("entries")}</span>
                  <span className={`chip ${ch.ok ? "ok" : "bad"}`}>
                    {ch.ok ? t("intact") : `${t("brokenAt")} ${ch.broken_at}`}
                  </span>
                </span>
              </div>
            ))}
            {!allOk && <p className="small err">{t("brokenBody")}</p>}
            {allOk && <p className="small muted">{t("intactBody")}</p>}
            {error && <p className="err small">{error}</p>}
          </div>
        </Panel>

        <Panel
          title={t("entriesTitle")}
          actions={
            <div className="field" style={{ minWidth: "12rem" }}>
              <select value={filter} onChange={(e) => setFilter(e.target.value)} aria-label={t("filter")}>
                {types.map((x) => <option key={x} value={x}>{x || t("allTypes")}</option>)}
              </select>
            </div>
          }
          flush
        >
          {!entries && <Empty>{c("loading")}</Empty>}
          {entries?.length === 0 && <Empty>{t("empty")}</Empty>}
          {entries && entries.length > 0 && (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr>
                    <th className="mono">{t("seq")}</th>
                    <th>{t("type")}</th>
                    <th>{t("process")}</th>
                    <th>{t("actor")}</th>
                    <th>{t("when")}</th>
                    <th className="mono">{t("prev")}</th>
                    <th className="mono">{t("hash")}</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={e.id}>
                      <td className="num">{e.seq}</td>
                      <td><span className={`chip ${TONE[e.entry_type] ?? "neutral"}`}>{e.entry_type}</span></td>
                      <td className="mono small">{e.process_id}</td>
                      <td className="small">{e.actor.id}<br /><span className="muted mono">{e.actor.kind}</span></td>
                      <td className="mono small">{when(e.ts)}</td>
                      <td className="mono small muted">{shortHash(e.prev_hash)}</td>
                      <td className="mono small">{shortHash(e.hash)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
