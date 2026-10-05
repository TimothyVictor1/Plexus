"use client";

import { useEffect, useState } from "react";

const KEY = "plexus.theme";
type Theme = "dark" | "light";

/** Dark is what Plexus is, so it is the default and light is a choice someone makes. */
function stored(): Theme {
  try {
    return window.localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark"; // a private window still gets a working console, just not a remembered one
  }
}

export default function ThemeToggle({ labels }: { labels: Record<string, string> }) {
  // Rendered dark on the server; the script in the layout has already set the real theme on
  // <html> before paint, so this only has to catch up with it, never cause the first paint.
  const [theme, setTheme] = useState<Theme>("dark");

  useEffect(() => setTheme(stored()), []);

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
    try {
      window.localStorage.setItem(KEY, next);
    } catch {
      /* not remembered, but still applied for this visit */
    }
  };

  const label = theme === "dark" ? labels.themeLight : labels.themeDark;

  return (
    <button className="rail-btn theme" type="button" onClick={toggle} aria-label={label} title={label}>
      {theme === "dark" ? (
        // Offer the sun when it is dark: the icon is what you get, not what you have.
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path
            strokeLinecap="round"
            d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.1 5.1l1.4 1.4M17.5 17.5l1.4 1.4M18.9 5.1l-1.4 1.4M6.5 17.5l-1.4 1.4"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M20 13.4A8.4 8.4 0 1 1 10.6 4a6.6 6.6 0 0 0 9.4 9.4Z"
          />
        </svg>
      )}
    </button>
  );
}
