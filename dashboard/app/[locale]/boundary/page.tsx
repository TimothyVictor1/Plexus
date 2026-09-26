"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import PageHeader from "@/components/PageHeader";
import { Panel } from "@/components/ui";
import { post } from "@/lib/api";

const SAMPLE = `Hej Erik,

Anna Lindqvist på Kustlogistik AB (556677-8899) har accepterat offerten.
Hennes personnummer är 850312-4565 och hon nås på +46 70 123 45 67
eller petra.sundin@kustlogistik.se.

Fakturan skickas till Hamngatan 14 i Karlskrona, betalning till
SE45 5000 0000 0583 9825 7466 eller bankgiro 5402-9981.

Can you create the ClickUp task before Friday?

/ Maja Öberg`;

type Found = { token: string; entity_type: string; in_vault: boolean };
type Result = { tokenised: string; found: Found[]; detected: number; leaks: [string, string][] };

export default function BoundaryPage() {
  const t = useTranslations("boundary");
  const [text, setText] = useState(SAMPLE);
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback((value: string) => {
    post<Result>("/pii/tokenise", { text: value })
      .then((r) => { setResult(r); setError(null); })
      .catch((e) => setError(String(e.message)));
  }, []);

  useEffect(() => {
    const id = setTimeout(() => run(text), 220);
    return () => clearTimeout(id);
  }, [text, run]);

  const highlighted = (result?.tokenised ?? "").split(/(<[A-Z]+_[0-9a-f]+>)/g);

  return (
    <>
      <PageHeader title={t("title")} sub={t("sub")} />
      <div className="content">
        <Panel
          title={t("panelTitle")}
          actions={<button className="ghost sm" onClick={() => setText(SAMPLE)}>{t("reset")}</button>}
        >
          <div className="grid2">
            <div className="stack">
              <label className="fl" htmlFor="src">{t("source")}</label>
              <textarea id="src" value={text} spellCheck={false} rows={16}
                        onChange={(e) => setText(e.target.value)} />
            </div>
            <div className="stack">
              <label className="fl">{t("modelSees")}</label>
              <div className="tokout">
                {highlighted.map((part, i) =>
                  /^<[A-Z]+_[0-9a-f]+>$/.test(part)
                    ? <span className="tok" key={i}>{part}</span>
                    : <span key={i}>{part}</span>,
                )}
              </div>
            </div>
          </div>

          {error && <p className="err" style={{ marginTop: ".7rem" }}>{error}</p>}

          <div className="inline" style={{ marginTop: ".9rem" }}>
            {result?.found.map((f) => (
              <span key={f.token} className="chip accent" title={f.in_vault ? t("inVault") : t("notInVault")}>
                {f.token} · {f.entity_type}
              </span>
            ))}
            {result && result.found.length === 0 && (
              <span className="chip neutral">{t("nothingFound")}</span>
            )}
          </div>

          <p className="small muted" style={{ marginTop: ".8rem" }}>
            {result?.leaks.length
              ? t("leakWarn", { n: result.leaks.length })
              : t("noLeak")}
          </p>
        </Panel>

        <Panel title={t("howTitle")}>
          <ul className="small" style={{ margin: 0, paddingLeft: "1.1rem", display: "flex", flexDirection: "column", gap: ".4rem" }}>
            <li>{t("how1")}</li>
            <li>{t("how2")}</li>
            <li>{t("how3")}</li>
          </ul>
        </Panel>
      </div>
    </>
  );
}
