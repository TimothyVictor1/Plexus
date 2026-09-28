"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import Tiles from "@/components/Tiles";
import { SearchIcon } from "@/components/shell/Icons";
import { get, type Home } from "@/lib/api";

function greetingKey(): "morning" | "afternoon" | "evening" {
  const h = new Date().getHours();
  return h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
}

const DOT: Record<string, string> = {
  smooth: "var(--good)", watch: "var(--warn)", slow: "var(--slow)",
};

export default function HomePage() {
  const t = useTranslations("home");
  const nav = useTranslations("shell");
  const tools = useTranslations("tools");
  const locale = useLocale();
  const router = useRouter();

  const [home, setHome] = useState<Home | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [part, setPart] = useState<"morning" | "afternoon" | "evening">("morning");

  useEffect(() => setPart(greetingKey()), []);
  useEffect(() => {
    get<Home>("/home").then(setHome).catch((e) => setError(String(e.message)));
  }, []);

  function ask() {
    const q = draft.trim();
    router.push(q ? `/${locale}/ask?q=${encodeURIComponent(q)}` : `/${locale}/ask`);
  }

  const stage = home?.status.stage;
  const ready = stage === "ready";
  const connected = home?.tools.filter((x) => x.connected) ?? [];
  const shown = (connected.length > 0 ? connected : (home?.tools ?? [])).slice(0, 4);

  return (
    <div style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      gap: 32, paddingTop: 44, paddingBottom: 12,
    }}>
      <h1 style={{ fontSize: "clamp(28px, 5vw, 44px)", fontWeight: 800, textAlign: "center" }}>
        {ready ? t(`greeting.${part}`) : t(`welcome.${part}`)}
      </h1>

      <div className="searchbar" style={{ width: "min(760px, 100%)" }}>
        <SearchIcon />
        <label htmlFor="homeAsk" className="sr-only">{nav.raw("askPlexus")}</label>
        <input
          id="homeAsk" className="input" value={draft} placeholder={t("askPlaceholder")}
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

      {error && <section className="card" style={{ width: "100%" }}><p className="err">{error}</p></section>}
      {!home && !error && <div className="skeleton" style={{ height: 120, width: "100%" }} />}

      {home && (
        <>
          <div className="card" style={{
            width: "100%", display: "flex", alignItems: "center", gap: 18,
            padding: "16px 22px", flexWrap: "wrap",
          }}>
            <span style={{ fontSize: 15, fontWeight: 600, flexGrow: 1 }}>
              {connected.length > 0
                ? t("learningFrom", { n: connected.length })
                : t("worksWithTools")}
            </span>
            {shown.map((tool) => (
              <span key={tool.category} style={{
                display: "flex", alignItems: "center", gap: 8, fontSize: 14, fontWeight: 600,
                color: tool.connected ? "var(--text)" : "var(--muted)",
              }}>
                <span style={{
                  width: 8, height: 8, borderRadius: 4,
                  background: tool.connected ? "var(--good)" : "var(--dim)",
                }} />
                {tools(tool.category)}
              </span>
            ))}
            <Link href={`/${locale}/connections`} className="btn secondary sm">
              {t("manage")}
            </Link>
          </div>

          <div className="grid-2" style={{ width: "100%" }}>
            <section className="card" style={{
              display: "flex", flexDirection: "column", gap: 12, minHeight: 250,
            }}>
              <div className="row" style={{ justifyContent: "space-between" }}>
                <h2>{t("needsYou")}</h2>
                {home.open_review_count > 0 && (
                  <span className="small muted">
                    {t("waiting", { n: home.open_review_count })}
                  </span>
                )}
              </div>

              {home.open_reviews.map((r) => (
                <Link key={r.id} href={`/${locale}/review`} className="sunken" style={{
                  display: "flex", justifyContent: "space-between", alignItems: "center",
                  gap: 12, textDecoration: "none", color: "var(--text)",
                }}>
                  <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 15, fontWeight: 600 }}>{r.title}</span>
                    <span className="small muted">{r.process_name}</span>
                  </span>
                  <span className="small" style={{ fontWeight: 600, color: "var(--accent)" }}>
                    {t("review")}
                  </span>
                </Link>
              ))}

              {ready && home.open_review_count === 0 && (
                <p className="muted">{t("caughtUp")}</p>
              )}
              {!ready && (
                <p className="muted" style={{ lineHeight: 1.5 }}>{t("nothingYet")}</p>
              )}
            </section>

            <section className="card" style={{
              display: "flex", flexDirection: "column", gap: 10, minHeight: 250,
            }}>
              <h2>{t("worthKnowing")}</h2>

              {home.insights.map((i) => (
                <Link key={i.kind + i.process_id} href={`/${locale}/work/${i.process_id}`} style={{
                  display: "flex", gap: 12, alignItems: "flex-start", padding: "10px 4px",
                  borderBottom: "1px solid var(--line)", textDecoration: "none",
                  color: "var(--text)",
                }}>
                  <span style={{
                    width: 9, height: 9, borderRadius: 5, marginTop: 7, flexShrink: 0,
                    background: DOT[i.health] ?? "var(--muted)",
                  }} />
                  <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <span style={{ fontSize: 15, fontWeight: 500, lineHeight: 1.4 }}>{i.text}</span>
                    <span className="small muted">{i.sub}</span>
                  </span>
                </Link>
              ))}

              {home.insights.length === 0 && (
                <div style={{
                  flexGrow: 1, display: "flex", flexDirection: "column", alignItems: "center",
                  justifyContent: "center", gap: 8, textAlign: "center",
                }}>
                  <span style={{ fontSize: 17, fontWeight: 700 }}>
                    {t(`stage.${stage ?? "no_connections"}.title`)}
                  </span>
                  <span className="small muted" style={{ maxWidth: 320, lineHeight: 1.5 }}>
                    {t(`stage.${stage ?? "no_connections"}.body`, {
                      connected: home.status.connected_count,
                      processes: home.status.process_count,
                      reviews: home.status.review_count,
                    })}
                  </span>
                  {stage === "no_connections" && (
                    <Link href={`/${locale}/connections`} className="btn secondary"
                          style={{ marginTop: 8 }}>
                      {t("connectFirst")}
                    </Link>
                  )}
                </div>
              )}
            </section>
          </div>
        </>
      )}
    </div>
  );
}
