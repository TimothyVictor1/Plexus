"use client";

import type { ReactNode } from "react";

export default function PageHeader({
  title, sub, actions,
}: { title: string; sub?: string; actions?: ReactNode }) {
  return (
    <header className="topbar">
      <div className="tt">
        <h1>{title}</h1>
        {sub && <span className="sub">{sub}</span>}
      </div>
      {actions && <div className="topacts">{actions}</div>}
    </header>
  );
}
