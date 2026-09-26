"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { AskIcon, ConnectIcon, ReviewIcon, SlowIcon, WorkIcon } from "./shell/Icons";

type Tile = { href: string; label: string; icon: ReactNode; bg: string; fg: string };

export default function Tiles({ locale, labels }: { locale: string; labels: Record<string, string> }) {
  const base = `/${locale}`;
  const tiles: Tile[] = [
    { href: `${base}/ask`, label: labels.ask, icon: <AskIcon />, bg: "var(--info-bg)", fg: "var(--info)" },
    { href: `${base}/work`, label: labels.work, icon: <WorkIcon />, bg: "var(--good-bg)", fg: "var(--good)" },
    { href: `${base}/review`, label: labels.review, icon: <ReviewIcon />, bg: "var(--alert-bg)", fg: "var(--alert)" },
    { href: `${base}/work?filter=slow`, label: labels.slowSpots, icon: <SlowIcon />, bg: "var(--warn-bg)", fg: "var(--warn)" },
    { href: `${base}/connections`, label: labels.connections, icon: <ConnectIcon />, bg: "var(--violet-bg)", fg: "var(--violet)" },
  ];

  return (
    <div style={{ display: "flex", gap: 28, justifyContent: "center", flexWrap: "wrap" }}>
      {tiles.map((t) => (
        <Link
          key={t.label}
          href={t.href}
          style={{
            width: 108, display: "flex", flexDirection: "column", alignItems: "center",
            gap: 12, color: "var(--text)", fontSize: 16, fontWeight: 600,
            textDecoration: "none", textAlign: "center",
          }}
        >
          <span style={{
            width: 64, height: 64, borderRadius: 16, background: t.bg, color: t.fg,
            display: "grid", placeItems: "center",
          }}>
            {t.icon}
          </span>
          {t.label}
        </Link>
      ))}
    </div>
  );
}
