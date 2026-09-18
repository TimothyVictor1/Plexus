import type { ReactNode } from "react";

// The locale layout renders <html>/<body>; this root layout only passes children through.
export default function RootLayout({ children }: { children: ReactNode }) {
  return children;
}
