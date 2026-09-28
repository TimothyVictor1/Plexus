import path from "node:path";
import { fileURLToPath } from "node:url";

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
  // The console is one package inside a repository that is mostly Python, and the host may
  // hand the whole repository to the build. Next then guesses a workspace root from whatever
  // lockfiles it finds, and it can guess wrong — which matters, because this is the root that
  // file tracing uses to decide what goes into the serverless bundle. Guessed too high and the
  // function is missing files it needs at runtime; the failure shows up only once deployed,
  // as FUNCTION_INVOCATION_FAILED, never in a local build. So say it outright.
  outputFileTracingRoot: path.dirname(fileURLToPath(import.meta.url)),
  // Only for self-hosted container builds. Vercel produces its own output.
  ...(process.env.NEXT_OUTPUT === "standalone" ? { output: "standalone" as const } : {}),
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
