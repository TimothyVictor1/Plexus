"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import type { ReviewItem } from "@/lib/api";

export default function ReviewCard({
  item, busy, onApprove, onSkip,
}: {
  item: ReviewItem;
  busy: boolean;
  onApprove: (id: string, editedText?: string) => void;
  onSkip: (id: string) => void;
}) {
  const t = useTranslations("review");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(item.draft_text);

  return (
    <article className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: "var(--accent)" }}>
          {item.process_name}
        </span>
        <h2 style={{ fontSize: 18 }}>{item.title}</h2>
        <p className="small muted" style={{ lineHeight: 1.45 }}>{item.why}</p>
      </div>

      {editing ? (
        <>
          <label className="sr-only" htmlFor={`draft-${item.id}`}>{t("editLabel")}</label>
          <textarea
            id={`draft-${item.id}`}
            className="sunken"
            style={{
              width: "100%", minHeight: 140, border: "1px solid var(--line-3)",
              color: "var(--text)", fontSize: 14, lineHeight: 1.55, resize: "vertical",
            }}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
        </>
      ) : (
        <div className="sunken" style={{ fontSize: 14, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
          {item.draft_text}
        </div>
      )}

      <div className="row">
        <button className="btn" disabled={busy} onClick={() => onApprove(item.id, editing ? draft : undefined)}>
          {editing ? t("approveEdited") : item.approve_label}
        </button>
        {!editing && (
          <button className="btn outline" disabled={busy} onClick={() => setEditing(true)}>
            {t("editFirst")}
          </button>
        )}
        {editing && (
          <button className="btn outline" disabled={busy}
                  onClick={() => { setEditing(false); setDraft(item.draft_text); }}>
            {t("cancelEdit")}
          </button>
        )}
        <button className="btn quiet" disabled={busy} onClick={() => onSkip(item.id)}>
          {t("skip")}
        </button>
      </div>
    </article>
  );
}
