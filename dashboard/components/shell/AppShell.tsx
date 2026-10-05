"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ApiError, REFRESH_EVENT, get, isPreview, type Org, type OrgStatus } from "@/lib/api";
import PageTransition from "./PageTransition";
import Rail from "./Rail";
import TopBar from "./TopBar";

const POLL_MS = 30_000;

export default function AppShell({
  locale, labels, children,
}: { locale: string; labels: Record<string, string>; children: ReactNode }) {
  const [org, setOrg] = useState<Org | null>(null);
  const [status, setStatus] = useState<OrgStatus | null>(null);
  const [offline, setOffline] = useState(false);
  // Preview is decided at runtime, not at build time: the console tries the real service
  // first and only falls back when it cannot be reached.
  const [preview, setPreview] = useState(false);

  const load = useCallback(() => {
    get<Org>("/org")
      .then((o) => { setOrg(o); setOffline(false); })
      .catch((e) => { setOrg(null); setOffline(e instanceof ApiError && e.offline); })
      .finally(() => setPreview(isPreview()));
    get<OrgStatus>("/org/status").then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    window.addEventListener(REFRESH_EVENT, load);
    return () => {
      clearInterval(id);
      window.removeEventListener(REFRESH_EVENT, load);
    };
  }, [load]);

  return (
    <div className="shell">
      <Rail locale={locale} labels={labels} reviewCount={status?.review_count ?? 0} />
      <div className="panel-main">
        <TopBar
          orgName={org?.display_name ?? labels.loadingOrg}
          isDemo={org?.is_demo ?? false}
          labels={labels}
        />
        {preview && (
          <div
            role="status"
            style={{
              marginTop: 14, padding: "12px 18px", borderRadius: "var(--radius-ctl)",
              background: "var(--accent-deep)", border: "1px solid var(--accent-edge)",
              display: "flex", flexWrap: "wrap", alignItems: "baseline", gap: "2px 8px",
            }}
          >
            <strong style={{ color: "var(--accent)" }}>{labels.previewTitle}</strong>
            <span className="small" style={{ lineHeight: 1.5 }}>{labels.previewBody}</span>
          </div>
        )}
        {!preview && offline && (
          <div
            role="status"
            style={{
              marginTop: 14, padding: "14px 18px", borderRadius: "var(--radius-ctl)",
              background: "var(--warn-bg)", border: "1px solid var(--warn)",
              display: "flex", flexDirection: "column", gap: 4,
            }}
          >
            <strong style={{ color: "var(--warn)" }}>{labels.offlineTitle}</strong>
            <span className="small" style={{ lineHeight: 1.5 }}>{labels.offlineBody}</span>
          </div>
        )}
        <PageTransition>{children}</PageTransition>
      </div>
    </div>
  );
}
