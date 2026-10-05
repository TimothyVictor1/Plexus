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
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
        <circle cx="12" cy="12" r="8.6" />
        {theme === "dark" ? (
          <path d="M12 3.4a8.6 8.6 0 0 0 0 17.2z" fill="currentColor" stroke="none" />
        ) : (
          <path d="M12 3.4a8.6 8.6 0 0 1 0 17.2z" fill="currentColor" stroke="none" />
        )}
      </svg>
    </button>
  );
}
