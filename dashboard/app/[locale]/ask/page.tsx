"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { SearchIcon } from "@/components/shell/Icons";
import { askStream, get, type AskMessage } from "@/lib/api";

function AskThread() {
  const t = useTranslations("ask");
  const params = useSearchParams();

  const [messages, setMessages] = useState<AskMessage[]>([]);
  const [chips, setChips] = useState<string[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const conversation = useRef<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const asked = useRef(false);

  useEffect(() => {
    get<string[]>("/ask/suggestions").then(setChips).catch(() => setChips([]));
  }, []);

  const ask = useCallback(async (question: string) => {
    const q = question.trim();
    if (!q || busy) return;
    setBusy(true);
    setError(null);
    setDraft("");
    setMessages((m) => [
      ...m,
      { role: "user", text: q },
      { role: "assistant", text: "", streaming: true },
    ]);

    try {
      const result = await askStream(q, conversation.current, (chunk) => {
        setMessages((m) => {
          const next = [...m];
          const last = next[next.length - 1];
          next[next.length - 1] = { ...last, text: last.text + chunk };
          return next;
        });
      });
      conversation.current = result.conversationId;
      setMessages((m) => {
        const next = [...m];
        next[next.length - 1] = {
          ...next[next.length - 1], streaming: false, sources: result.sources,
        };
        return next;
      });
    } catch (e) {
      setError(String((e as Error).message));
      setMessages((m) => m.slice(0, -1));
    } finally {
      setBusy(false);
    }
  }, [busy]);

  // A question typed on Home arrives here as ?q=
  useEffect(() => {
    const q = params.get("q");
    if (q && !asked.current) {
      asked.current = true;
      void ask(q);
    }
  }, [params, ask]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <div className="page centered">
      <div className="page-head">
        <h1>{t("title")}</h1>
        <p>{t("sub")}</p>
      </div>

      {messages.length === 0 && chips.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {chips.map((c) => (
            <button
              key={c}
              onClick={() => ask(c)}
              style={{
                minHeight: 44, padding: "0 18px", border: "1px solid var(--line-2)",
                borderRadius: 22, background: "var(--card)", fontSize: 14,
                color: "var(--text)",
              }}
            >
              {c}
            </button>
          ))}
        </div>
      )}

      {messages.map((m, i) => (
        <div key={i} style={{
          display: "flex", flexDirection: "column", gap: 6,
          alignItems: m.role === "user" ? "flex-end" : "flex-start",
        }}>
          <div style={{
            maxWidth: 600, padding: "14px 18px", borderRadius: 16,
            fontSize: 15, lineHeight: 1.55, whiteSpace: "pre-wrap",
            background: m.role === "user" ? "var(--accent)" : "var(--card)",
            color: m.role === "user" ? "var(--on-accent)" : "var(--text)",
            border: m.role === "user" ? "none" : "1px solid var(--line-2)",
          }}>
            {m.text}
            {m.streaming && <span aria-hidden="true"> ▌</span>}
          </div>
          {m.sources && m.sources.length > 0 && (
            <div className="small muted">
              {t("from", { sources: [...new Set(m.sources.map((s) => s.tool))].join(", ") })}
            </div>
          )}
        </div>
      ))}

      <div ref={endRef} />

      {error && <p className="err">{error}</p>}

      <div className="searchbar">
        <SearchIcon />
        <label htmlFor="askInput" className="sr-only">{t("yourQuestion")}</label>
        <input
          id="askInput" className="input" value={draft} placeholder={t("placeholder")}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask(draft)}
        />
        <button className="btn" disabled={busy} onClick={() => ask(draft)}>
          {busy ? t("thinking") : t("askButton")}
        </button>
      </div>
    </div>
  );
}

export default function AskPage() {
  return (
    <Suspense fallback={<div className="page"><div className="skeleton" style={{ height: 200 }} /></div>}>
      <AskThread />
    </Suspense>
  );
}
