"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AskIcon, ConnectIcon, HomeIcon, PlexusMark, PlusIcon, ReviewIcon, SettingsIcon, TwinIcon,
  WorkIcon,
} from "./Icons";

type Item = { href: string; label: string; icon: React.ReactNode; badge?: number };

export default function Rail({
  locale, labels, reviewCount,
}: { locale: string; labels: Record<string, string>; reviewCount: number }) {
  const pathname = usePathname();
  const base = `/${locale}`;

  const items: Item[] = [
    { href: base, label: labels.home, icon: <HomeIcon /> },
    { href: `${base}/ask`, label: labels.ask, icon: <AskIcon /> },
    { href: `${base}/work`, label: labels.work, icon: <WorkIcon /> },
    { href: `${base}/review`, label: labels.review, icon: <ReviewIcon />, badge: reviewCount },
    { href: `${base}/twin`, label: labels.twin, icon: <TwinIcon /> },
    { href: `${base}/connections`, label: labels.connections, icon: <ConnectIcon /> },
  ];

  const isCurrent = (href: string) =>
    href === base ? pathname === base : pathname.startsWith(href);

  return (
    <nav className="rail" aria-label={labels.mainNav}>
      <span className="rail-mark"><PlexusMark /></span>

      <Link href={`${base}/ask`} className="rail-btn primary" aria-label={labels.askPlexus}
            title={labels.askPlexus}>
        <PlusIcon />
      </Link>

      {items.map((item) => (
        <Link
          key={item.href}
          href={item.href}
          className="rail-btn"
          aria-label={item.label}
          title={item.label}
          aria-current={isCurrent(item.href) ? "page" : undefined}
        >
          {item.icon}
          {item.badge !== undefined && item.badge > 0 && (
            <span className="rail-badge" aria-hidden="true">{item.badge}</span>
          )}
          {item.badge !== undefined && item.badge > 0 && (
            <span className="sr-only">{labels.waitingCount.replace("{n}", String(item.badge))}</span>
          )}
        </Link>
      ))}

      <span className="rail-spacer" />
      <span className="rail-sep" />
      <Link href={`${base}/settings`} className="rail-btn" aria-label={labels.settings}
            title={labels.settings} aria-current={isCurrent(`${base}/settings`) ? "page" : undefined}>
        <SettingsIcon />
      </Link>
    </nav>
  );
}
