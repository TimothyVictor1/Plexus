"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { get, type Org, type OrgStatus } from "@/lib/api";

export default function SettingsPage() {
  const t = useTranslations("settings");
  const locale = useLocale();
  const [org, setOrg] = useState<Org | null>(null);
  const [status, setStatus] = useState<OrgStatus | null>(null);

  useEffect(() => {
    get<Org>("/org").then(setOrg).catch(() => setOrg(null));
    get<OrgStatus>("/org/status").then(setStatus).catch(() => setStatus(null));
  }, []);

  return (
    <div className="page">
      <div className="page-head">
        <h1>{t("title")}</h1>
        <p>{t("sub")}</p>
      </div>

      <section className="card stack">
        <h2>{t("organisation")}</h2>
        <dl style={{
          display: "grid", gridTemplateColumns: "auto 1fr", gap: "6px 20px", margin: 0,
        }}>
          <dt className="small muted">{t("name")}</dt>
          <dd style={{ margin: 0 }}>{org?.display_name ?? "—"}</dd>
          <dt className="small muted">{t("language")}</dt>
          <dd style={{ margin: 0 }}>{org?.locale ?? "—"}</dd>
          <dt className="small muted">{t("dataset")}</dt>
          <dd style={{ margin: 0 }}>{org?.is_demo ? t("exampleData") : t("realData")}</dd>
          <dt className="small muted">{t("toolsConnected")}</dt>
          <dd style={{ margin: 0 }}>{status?.connected_count ?? "—"}</dd>
        </dl>
      </section>

      <section className="card stack">
        <h2>{t("advanced")}</h2>
        <p className="small muted" style={{ lineHeight: 1.5 }}>{t("advancedBody")}</p>
        <Link href={`/${locale}/settings/advanced`} className="btn secondary"
              style={{ alignSelf: "flex-start" }}>
          {t("openAdvanced")}
        </Link>
      </section>
    </div>
  );
}
