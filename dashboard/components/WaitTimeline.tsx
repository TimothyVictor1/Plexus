"use client";

import { useTranslations } from "next-intl";
import type { Step, Wait } from "@/lib/api";

/** Steps left to right with the wait between each pair drawn to scale.
 *  The bar height carries the duration, and the slowest one is called out in words too,
 *  so the meaning never depends on noticing a colour. */
export default function WaitTimeline({ steps, waits }: { steps: Step[]; waits: Wait[] }) {
  const t = useTranslations("process");
  const longest = Math.max(1, ...waits.map((w) => w.duration.seconds));

  return (
    <div style={{ display: "flex", alignItems: "flex-start", overflowX: "auto", paddingBottom: 4 }}>
      {steps.map((step, i) => {
        const wait = waits[i];
        const height = wait
          ? Math.max(3, Math.round((wait.duration.seconds / longest) * 10))
          : 3;
        return (
          <div
            key={step.verb + step.order}
            style={{ display: "flex", alignItems: "flex-start", flexGrow: wait ? 1 : 0 }}
          >
            <div style={{
              width: 108, flexShrink: 0, display: "flex", flexDirection: "column",
              alignItems: "center", gap: 10, textAlign: "center",
            }}>
              <span style={{
                width: 32, height: 32, borderRadius: 16, background: "var(--accent-soft)",
                color: "var(--accent)", fontSize: 14, fontWeight: 700,
                display: "grid", placeItems: "center",
              }}>
                {step.order}
              </span>
              <span style={{ fontSize: 13, fontWeight: 600, lineHeight: 1.3 }}>{step.label}</span>
            </div>

            {wait && (
              <div style={{
                flexGrow: 1, minWidth: 56, display: "flex", flexDirection: "column",
                alignItems: "center", gap: 6, paddingTop: 6,
              }}>
                <span style={{
                  fontSize: 13, fontWeight: 700,
                  color: wait.is_slowest ? "var(--slow)" : "var(--accent-edge)",
                }}>
                  {wait.duration.text}
                </span>
                <span style={{
                  width: "100%", height, borderRadius: 3,
                  background: wait.is_slowest ? "var(--slow)" : "var(--accent-edge)",
                }} />
                {wait.is_slowest && (
                  <span style={{ fontSize: 12, fontWeight: 700, color: "var(--slow)" }}>
                    {t("slowest")}
                  </span>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
