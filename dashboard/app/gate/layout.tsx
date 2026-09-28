import type { ReactNode } from "react";
import { Plus_Jakarta_Sans } from "next/font/google";

import "../globals.css";

// The console's <html>/<body> live in the locale layout, which the gate deliberately sits
// outside of, so it brings its own. The language is set on the client once the notice knows
// which one it is showing: a layout cannot read the query string.
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-jakarta",
});

export const metadata = { title: "Plexus" };

export default function GateLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={jakarta.variable}>
      <body>{children}</body>
    </html>
  );
}
