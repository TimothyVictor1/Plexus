"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import ProcessCard from "@/components/ProcessCard";
import { get, type ProcessSummary } from "@/lib/api";

function WorkList() {
  const t = useTranslations("work");
  const locale = useLocale();
  const params = useSearchParams();
  const onlySlow = params.get("filter") === "slow";

  const [items, setItems] = useState<ProcessSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setItems(null);
    get<{ processes: ProcessSummary[] }>(`/processes?filter=${onlySlow ? "slow" : "all"}`)
      .then((d) => setItems(d.processes))
      .catch((e) => setError(String(e.message)));
  }, [onlySlow]);
  useEffect(load, [load]);

  return (
    <div className="page">
      <div className="page-head">
        <h1>{onlySlow ? t("slowTitle") : t("title")}</h1>
        <p>{onlySlow ? t("slowSub") : t("sub")}</p>
      </div>

      {error && <section className="card"><p className="err">{error}</p></section>}

      {!items && !error && (
        <div className="grid-3">
          {[0, 1, 2].map((n) => <div key={n} className="skeleton" style={{ height: 168 }} />)}
        </div>
      )}

      {items?.length === 0 && (
        <section className="card">
          <p className="muted" style={{ lineHeight: 1.55 }}>
            {onlySlow ? t("noSlow") : t("empty")}
          </p>
        </section>
      )}

      {items && items.length > 0 && (
        <div className="grid-3">
          {items.map((p) => <ProcessCard key={p.id} process={p} locale={locale} />)}
        </div>
      )}
    </div>
  );
}

export default function WorkPage() {
  return (
    <Suspense fallback={<div className="page"><div className="skeleton" style={{ height: 200 }} /></div>}>
      <WorkList />
    </Suspense>
  );
}
