"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { ProcessSummary } from "@/lib/api";
import LevelBars from "./LevelBars";

export default function ProcessCard({
  process, locale,
}: { process: ProcessSummary; locale: string }) {
  const t = useTranslations("work");
  const health = useTranslations("health");

  const slowest = process.slowest.text
    ? process.slowest.text.charAt(0).toLowerCase() + process.slowest.text.slice(1)
    : "";

  return (
    <Link
      href={`/${locale}/work/${process.id}`}
      className="card bordered"
      style={{
        display: "flex", flexDirection: "column", gap: 14,
        textDecoration: "none", color: "var(--text)",
      }}
    >
      <span className={`chip ${process.health}`} style={{ alignSelf: "flex-start" }}>
        {health(process.health)}
      </span>

      <span style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 17, fontWeight: 700 }}>{process.name}</span>
        <span className="small muted" style={{ lineHeight: 1.45 }}>
          {t("takes", { time: process.total_duration.text })}
          {slowest ? ` ${t("slowest", { what: slowest })}` : ""}
        </span>
      </span>

      <span
        style={{
          display: "flex", alignItems: "center", gap: 10, paddingTop: 12,
          borderTop: "1px solid var(--line)", width: "100%",
        }}
      >
        <LevelBars level={process.level} paused={process.paused} />
        <span className="small muted">
          {process.paused ? t("isPaused") : t("plexusDoes", { level: t(`level.${process.level}`) })}
        </span>
      </span>
    </Link>
  );
}
