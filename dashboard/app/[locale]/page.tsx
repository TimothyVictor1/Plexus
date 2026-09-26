"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import Tiles from "@/components/Tiles";
import { SearchIcon } from "@/components/shell/Icons";
import { get, type OrgStatus } from "@/lib/api";

function greetingKey(): "morning" | "afternoon" | "evening" {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}

export default function HomePage() {
  const t = useTranslations("home");
  const nav = useTranslations("shell");
  const locale = useLocale();
  const router = useRouter();
  const [status, setStatus] = useState<OrgStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [part, setPart] = useState<"morning" | "afternoon" | "evening">("morning");

  useEffect(() => setPart(greetingKey()), []);
  useEffect(() => {
    get<OrgStatus>("/org/status").then(setStatus).catch((e) => setError(String(e.message)));
  }, []);

  function ask() {
    const q = draft.trim();
    router.push(q ? `/${locale}/ask?q=${encodeURIComponent(q)}` : `/${locale}/ask`);
  }

  const stage = status?.stage;
  const greeting = stage === "ready" ? t(`greeting.${part}`) : t(`welcome.${part}`);

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      gap: 36, paddingTop: 52,
    }}>
      <h1 style={{ fontSize: "clamp(28px, 5vw, 44px)", fontWeight: 800, textAlign: "center" }}>
        {greeting}
      </h1>

      <div className="searchbar" style={{ width: "min(760px, 100%)" }}>
        <SearchIcon />
        <label htmlFor="homeAsk" className="sr-only">{nav.raw("askPlexus")}</label>
        <input
          id="homeAsk"
          className="input"
          value={draft}
          placeholder={t("askPlaceholder")}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
        />
        <button className="btn" onClick={ask}>{t("askButton")}</button>
      </div>

      <Tiles
        locale={locale}
        labels={{
          ask: nav.raw("ask"), work: nav.raw("work"), review: nav.raw("review"),
          slowSpots: t("slowSpots"), connections: nav.raw("connections"),
        }}
      />

      <section className="card" style={{ width: "100%", maxWidth: 960 }}>
        {error && <p className="err">{error}</p>}
        {!error && !status && <p className="muted">{t("loading")}</p>}
        {status && (
          <div className="stack" style={{ gap: 8 }}>
            <h2>{t(`stage.${status.stage}.title`)}</h2>
            <p className="muted" style={{ lineHeight: 1.55 }}>
              {t(`stage.${status.stage}.body`, {
                connected: status.connected_count,
                processes: status.process_count,
                reviews: status.review_count,
              })}
            </p>
            {status.stage === "no_connections" && (
              <a className="btn secondary" href={`/${locale}/connections`}
                 style={{ alignSelf: "flex-start", marginTop: 8 }}>
                {t("connectFirst")}
              </a>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
