"use client";

/** A mark per category. Drawn rather than fetched, so the gallery has no external images
 *  and looks the same offline. */
const PATHS: Record<string, string> = {
  email: "M3 7l9 6 9-6M4 5h16a1 1 0 0 1 1 1v12a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z",
  calendar: "M7 3v4M17 3v4M4 9h16M5 5h14a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z",
  crm: "M16 19v-1a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v1M9.5 7.5a3 3 0 1 0 0-.01zM19 11h3M20.5 9.5v3",
  accounting: "M7 7h10M7 11h10M7 15h6M5 3h14a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z",
  files: "M4 7a1 1 0 0 1 1-1h4l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z",
  hr: "M12 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM5 20a7 7 0 0 1 14 0",
  chat: "M5 5h14a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-8l-5 4v-4H5a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z",
  projects: "M4 6h16M4 12h16M4 18h10M8 4v4M16 10v4",
};

const TINT: Record<string, [string, string]> = {
  email: ["var(--info-bg)", "var(--info)"],
  calendar: ["var(--violet-bg)", "var(--violet)"],
  crm: ["var(--good-bg)", "var(--good)"],
  accounting: ["var(--warn-bg)", "var(--warn)"],
  files: ["var(--info-bg)", "var(--info)"],
  hr: ["var(--alert-bg)", "var(--alert)"],
  chat: ["var(--violet-bg)", "var(--violet)"],
  projects: ["var(--good-bg)", "var(--good)"],
};

export default function ConnectorIcon({
  category, size = 40,
}: { category: string; size?: number }) {
  const [bg, fg] = TINT[category] ?? ["var(--raised-2)", "var(--muted)"];
  return (
    <span
      aria-hidden="true"
      style={{
        width: size, height: size, borderRadius: size * 0.3, background: bg, color: fg,
        display: "grid", placeItems: "center", flexShrink: 0,
      }}
    >
      <svg width={size * 0.5} height={size * 0.5} viewBox="0 0 24 24" fill="none"
           stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d={PATHS[category] ?? "M5 12h14"} />
      </svg>
    </span>
  );
}
