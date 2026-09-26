"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PageHeader from "@/components/PageHeader";
import { Empty, Panel } from "@/components/ui";
import { get } from "@/lib/api";

type Node = { key: string; kind: string; title: string; confidence?: number; status?: string; provenance?: string };
type Neighbourhood = {
  nodes: { key: string; kind: string; title: string; properties: Record<string, unknown> }[];
  edges: { type: string; from: string; to: string }[];
};

export default function GraphPage() {
  const t = useTranslations("graph");
  const c = useTranslations("common");
  const [q, setQ] = useState("");
  const [nodes, setNodes] = useState<Node[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [hood, setHood] = useState<Neighbourhood | null>(null);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback((query: string) => {
    get<{ nodes: Node[] }>(`/graph/nodes?q=${encodeURIComponent(query)}`)
      .then((d) => setNodes(d.nodes))
      .catch((e) => setError(String(e.message)));
  }, []);

  useEffect(() => {
    const id = setTimeout(() => search(q), 220);
    return () => clearTimeout(id);
  }, [q, search]);

  useEffect(() => {
    if (!selected) { setHood(null); return; }
    get<Neighbourhood>(`/graph/nodes/${encodeURIComponent(selected)}?depth=1`)
      .then(setHood)
      .catch((e) => setError(String(e.message)));
  }, [selected]);

  return (
    <>
      <PageHeader title={t("title")} sub={t("sub")} />
      <div className="content">
        {error && <Panel><p className="err">{error}</p></Panel>}
        <div className="grid2">
          <Panel
            title={t("nodes")}
            actions={
              <div className="field" style={{ minWidth: "13rem" }}>
                <input type="search" value={q} placeholder={t("search")}
                       onChange={(e) => setQ(e.target.value)} aria-label={t("search")} />
              </div>
            }
            flush
          >
            {!nodes && <Empty>{c("loading")}</Empty>}
            {nodes?.length === 0 && <Empty>{t("noNodes")}</Empty>}
            {nodes && nodes.length > 0 && (
              <div className="tablewrap" style={{ maxHeight: "34rem", overflowY: "auto" }}>
                <table>
                  <thead><tr><th>{t("kind")}</th><th>{t("title")}</th><th className="mono">{t("conf")}</th></tr></thead>
                  <tbody>
                    {nodes.map((n) => (
                      <tr key={n.key} onClick={() => setSelected(n.key)}
                          style={{ cursor: "pointer",
                                   background: selected === n.key ? "var(--accent-soft)" : undefined }}>
                        <td><span className="chip neutral">{n.kind}</span></td>
                        <td className="small">{n.title}<br /><span className="mono muted" style={{ fontSize: ".72rem" }}>{n.key}</span></td>
                        <td className="num">{n.confidence?.toFixed(2) ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title={t("neighbourhood")}>
            {!selected && <Empty>{t("pick")}</Empty>}
            {selected && !hood && <Empty>{c("loading")}</Empty>}
            {hood && (
              <div className="stack">
                <dl className="kv">
                  <dt>{t("selected")}</dt><dd className="mono">{selected}</dd>
                  <dt>{t("connected")}</dt><dd>{hood.nodes.length}</dd>
                  <dt>{t("relations")}</dt><dd>{hood.edges.length}</dd>
                </dl>
                <span className="eyebrow">{t("edges")}</span>
                <div className="tablewrap" style={{ maxHeight: "16rem", overflowY: "auto" }}>
                  <table>
                    <tbody>
                      {hood.edges.map((e, i) => (
                        <tr key={i}>
                          <td className="mono small">{e.from}</td>
                          <td><span className="chip accent">{e.type}</span></td>
                          <td className="mono small">{e.to}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <span className="eyebrow">{t("provenanceNote")}</span>
              </div>
            )}
          </Panel>
        </div>
      </div>
    </>
  );
}
