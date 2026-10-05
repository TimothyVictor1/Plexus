import type { ReactNode } from "react";

import "./landing.css";

/* The landing page brings its own <html>/<body>: the console's live in the locale layout, and
   this page shares none of its chrome. The display face is loaded from a CDN because it is not
   ours to redistribute; Geist Pixel Circle is the local fallback behind it. */
export const metadata = {
  title: "The Nervous System For Your Company",
  description:
    "One AI layer that connects your existing tools, learns your company's context and keeps your data in Europe.",
};

export default function LandingLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      {/* The rule below is a Pages Router rule about _document; this is a route-group layout
          in the App Router, where loading a face for one route is the point. */}
      {/* eslint-disable @next/next/no-page-custom-font */}
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://db.onlinewebfonts.com/c/8cb707a9b8a73f8a7403336b861c3074?family=BubbledotICG-FinePos"
          rel="stylesheet"
        />
        <link
          href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css"
          rel="stylesheet"
          integrity="sha512-SnH5WK+bZxgPHs44uWIX+LLJAJ9/2PkPKZ5QiAj6Ta86w+fsb2TkcmfRyVX3pBnMFcV7oQPJkl9QevSCWr3W6A=="
          crossOrigin="anonymous"
          referrerPolicy="no-referrer"
        />
      </head>
      {/* eslint-enable @next/next/no-page-custom-font */}
      <body className="landing-body">{children}</body>
    </html>
  );
}
