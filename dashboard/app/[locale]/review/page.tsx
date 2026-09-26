"use client";

import { useTranslations } from "next-intl";

export default function Page() {
  const t = useTranslations("placeholder");
  const p = useTranslations("pages");
  return (
    <div className="page">
      <div className="page-head">
        <h1>{p("review.title")}</h1>
        <p>{p("review.sub")}</p>
      </div>
      <section className="card">
        <p className="muted" style={{ lineHeight: 1.55 }}>{t("body")}</p>
      </section>
    </div>
  );
}
