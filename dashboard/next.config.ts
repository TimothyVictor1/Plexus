import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./i18n/request.ts");

// The old technical route names redirect to the plain-language ones.
const moved: [string, string][] = [
  ["processes", "work"],
  ["inbox", "review"],
  ["adapters", "connections"],
  ["boundary", "connections"],
  ["graph", "settings/advanced"],
  ["ledger", "settings/advanced"],
];

const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // `next build` and `next dev` share .next by default, so building while the dev server is
  // running leaves it requiring vendor chunks the build has already replaced. Separate
  // directories remove the collision entirely.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  async redirects() {
    return moved.flatMap(([from, to]) => [
      { source: `/:locale(sv|en)/${from}`, destination: `/:locale/${to}`, permanent: true },
      { source: `/:locale(sv|en)/${from}/:rest*`, destination: `/:locale/${to}`, permanent: true },
    ]);
  },
};

export default withNextIntl(nextConfig);
