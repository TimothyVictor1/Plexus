"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PageHeader from "@/components/PageHeader";
import { Empty, Panel, when } from "@/components/ui";
import { get, post } from "@/lib/api";

type Adapter = { id: string; documents: number; write_enabled: boolean };
type Record_ = { external_id: string; record_type: string; fields: Record<string, unknown>; updated_at: string };
type Execution = {
  id: string; operation: string; process_id: string;
  approver: { subject: string } | null;
  write_result: { ok: boolean; message: string }; reversed_at: string | null; created_at: string;
};

export default function AdaptersPage() {
  const t = useTranslations("adapters");
  const c = useTranslations("common");
  const [adapters, setAdapters] = useState<Adapter[] | null>(null);
  const [records, setRecords] = useState<Record_[]>([]);
  const [execs, setExecs] = useState<Execution[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    get<{ adapters: Adapter[]; records: Record_[] }>("/adapters")
      .then((d) => { setAdapters(d.adapters); setRecords(d.records); })
      .catch((e) => setError(String(e.message)));
    get<{ executions: Execution[] }>("/executions")
      .then((d) => setExecs(d.executions))
      .catch(() => undefined);
  }, []);
  useEffect(load, [load]);

  async function reverse(id: string) {
    setBusy(true); setError(null);
    try {
      await post(`/executions/${id}/reverse`);
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
        {error && <Panel><p className="err">{error}</p></Panel>}

        <Panel title={t("connected")} flush>
          {!adapters && <Empty>{c("loading")}</Empty>}
          {adapters && (
            <div className="tablewrap">
              <table>
                <thead><tr><th>{t("adapter")}</th><th className="mono">{t("documents")}</th><th>{t("write")}</th></tr></thead>
                <tbody>
                  {adapters.map((a) => (
                    <tr key={a.id}>
                      <td className="mono">{a.id}</td>
                      <td className="num">{a.documents}</td>
                      <td>
                        <span className={`chip ${a.write_enabled ? "warn" : "neutral"}`}>
                          {a.write_enabled ? t("enabled") : t("readOnly")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title={t("executionsTitle")} flush>
          {execs.length === 0 && <Empty>{t("noExecutions")}</Empty>}
          {execs.length > 0 && (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr><th>{t("operation")}</th><th>{t("approver")}</th><th>{t("when")}</th>
                      <th>{t("status")}</th><th /></tr>
                </thead>
                <tbody>
                  {execs.map((e) => (
                    <tr key={e.id}>
                      <td className="mono small">{e.operation}<br /><span className="muted">{e.process_id}</span></td>
                      <td className="small">{e.approver?.subject ?? t("automatic")}</td>
                      <td className="mono small">{when(e.created_at)}</td>
                      <td>
                        <span className={`chip ${e.reversed_at ? "bad" : "ok"}`}>
                          {e.reversed_at ? t("reversed") : t("live")}
                        </span>
                      </td>
                      <td>
                        {!e.reversed_at && (
                          <button className="ghost sm" disabled={busy} onClick={() => reverse(e.id)}>
                            {t("reverse")}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title={t("recordsTitle")} flush>
          {records.length === 0 && <Empty>{t("noRecords")}</Empty>}
          {records.length > 0 && (
            <div className="tablewrap">
              <table>
                <thead>
                  <tr><th className="mono">{t("id")}</th><th>{t("type")}</th>
                      <th>{t("fields")}</th><th>{t("updated")}</th></tr>
                </thead>
                <tbody>
                  {records.map((r) => (
                    <tr key={r.external_id}>
                      <td className="mono small">{r.external_id}</td>
                      <td><span className="chip neutral">{r.record_type}</span></td>
                      <td className="mono small">
                        {Object.entries(r.fields)
                          .filter(([k]) => !k.startsWith("_"))
                          .slice(0, 4)
                          .map(([k, v]) => `${k}=${String(v)}`)
                          .join("  ")}
                      </td>
                      <td className="mono small">{when(r.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="small muted" style={{ padding: ".8rem" }}>{t("recordsNote")}</p>
        </Panel>
      </div>
    </>
  );
}
