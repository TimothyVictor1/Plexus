"use client";

export default function LevelBars({
  level, paused = false,
}: { level: number; paused?: boolean }) {
  return (
    <span className="dots" aria-hidden="true">
      {[1, 2, 3, 4, 5].map((n) => (
        <span
          key={n}
          className={`dot${n <= level ? (paused ? " paused" : " on") : ""}`}
        />
      ))}
    </span>
  );
}
