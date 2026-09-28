"use client";

import { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import ReviewCard from "@/components/ReviewCard";
import { get, post, signalRefresh, type ReviewDecision, type ReviewItem } from "@/lib/api";

export default function ReviewPage() {
  const t = useTranslations("review");
  const [open, setOpen] = useState<ReviewItem[] | null>(null);
  const [done, setDone] = useState<ReviewItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<ReviewDecision | null>(null);

  const load = useCallback(() => {
    get<{ open: ReviewItem[]; done_today: ReviewItem[] }>("/review")
      .then((d) => { setOpen(d.open); setDone(d.done_today); })
      .catch((e) => setError(String(e.message)));
  }, []);
  useEffect(load, [load]);

  async function decide(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      setLast(await post<ReviewDecision>(path, body));
      load();
      signalRefresh();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page wide-centered">
      <div className="page-head">
        <h1>{t("title")}</h1>
        <p>{t("sub")}</p>
      </div>

      {error && <section className="card"><p className="err">{error}</p></section>}

      {last && (
        <section className="card" style={{ borderLeft: `3px solid ${last.ok ? "var(--good)" : "var(--warn)"}` }}>
          <strong>{last.title}</strong>
          <p className="small muted" style={{ marginTop: 4, lineHeight: 1.5 }}>{last.detail}</p>
        </section>
      )}

      {!open && !error && <div className="skeleton" style={{ height: 200 }} />}

      {open?.length === 0 && (
        <section className="card"><p style={{ fontSize: 16 }}>{t("allCaughtUp")}</p></section>
      )}

      {open?.map((item) => (
        <ReviewCard
          key={item.id}
          item={item}
          busy={busy}
          onApprove={(id, edited) =>
            decide(`/review/${id}/approve`, edited ? { edited_text: edited } : {})
          }
          onSkip={(id) => decide(`/review/${id}/skip`)}
        />
      ))}

      {done.length > 0 && (
        <div className="stack" style={{ gap: 8 }}>
          <h2 className="small muted" style={{ fontWeight: 700 }}>{t("doneToday")}</h2>
          {done.map((d) => (
            <div key={d.id} className="card" style={{
              display: "flex", justifyContent: "space-between", gap: 12,
              padding: "12px 16px", fontSize: 14,
            }}>
              <span>{d.title}</span>
              <span className="muted">{t(`status.${d.status}`)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
