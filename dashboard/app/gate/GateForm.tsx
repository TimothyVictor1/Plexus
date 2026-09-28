"use client";

import { useEffect, useState, type FormEvent } from "react";

type Copy = {
  title: string;
  lead: string;
  terms: string[];
  accept: string;
  passwordLabel: string;
  passwordPlaceholder: string;
  submit: string;
  working: string;
  wrongPassword: string;
  mustAccept: string;
  failed: string;
  footer: string;
};

export default function GateForm({
  t,
  next,
  otherLocale,
  locale,
}: {
  t: Copy;
  next: string;
  otherLocale: string;
  locale: string;
}) {
  const [password, setPassword] = useState("");
  const [accepted, setAccepted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // The layout cannot read the query string, so the page that does tells the document.
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!accepted) {
      setError(t.mustAccept);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/gate", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ password, accepted }),
      });
      if (res.ok) {
        // A full navigation, so the middleware sees the new cookie on the way in.
        window.location.href = next;
        return;
      }
      const body = (await res.json().catch(() => ({}))) as { reason?: string };
      setError(body.reason === "wrong_password" ? t.wrongPassword : t.failed);
    } catch {
      setError(t.failed);
    }
    setBusy(false);
  }

  return (
    <main className="gate">
      <form className="gate-card" onSubmit={submit}>
        <p className="gate-mark">Plexus</p>
        <h1>{t.title}</h1>
        <p className="gate-lead">{t.lead}</p>

        <ul className="gate-terms">
          {t.terms.map((term) => (
            <li key={term}>{term}</li>
          ))}
        </ul>

        <label className="gate-accept">
          <input
            type="checkbox"
            checked={accepted}
            onChange={(e) => setAccepted(e.target.checked)}
          />
          <span>{t.accept}</span>
        </label>

        <label className="gate-field">
          <span>{t.passwordLabel}</span>
          <input
            type="password"
            value={password}
            autoComplete="current-password"
            placeholder={t.passwordPlaceholder}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && <p className="gate-error">{error}</p>}

        <button className="gate-button" type="submit" disabled={busy || !accepted || !password}>
          {busy ? t.working : t.submit}
        </button>

        <p className="gate-footer">
          {t.footer}
          <a href={`/gate?next=${encodeURIComponent(next)}&locale=${otherLocale}`}>
            {otherLocale === "sv" ? "Svenska" : "English"}
          </a>
        </p>
      </form>
    </main>
  );
}
