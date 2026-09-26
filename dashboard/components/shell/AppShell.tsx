"use client";

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { get, type Org, type OrgStatus } from "@/lib/api";
import Rail from "./Rail";
import TopBar from "./TopBar";

const POLL_MS = 30_000;

export default function AppShell({
  locale, labels, children,
}: { locale: string; labels: Record<string, string>; children: ReactNode }) {
  const [org, setOrg] = useState<Org | null>(null);
  const [status, setStatus] = useState<OrgStatus | null>(null);

  const load = useCallback(() => {
    get<Org>("/org").then(setOrg).catch(() => setOrg(null));
    get<OrgStatus>("/org/status").then(setStatus).catch(() => setStatus(null));
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, POLL_MS);
    return () => clearInterval(id);
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
        {children}
      </div>
    </div>
  );
}
