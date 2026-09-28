import createMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";

import { routing } from "./i18n/routing";
import { GATE_COOKIE, GATE_PATH, gateEnabled, verifyGateToken } from "./lib/gate";

const intl = createMiddleware(routing);

/** Nothing is served until the notice has been accepted and the password entered.
 *
 *  The check runs here rather than in a page, so it covers every route at once and a visitor
 *  never receives the markup of a screen they have not unlocked. The gate itself and /api are
 *  outside the matcher below, so they stay reachable.
 */
export default async function middleware(request: NextRequest): Promise<NextResponse> {
  if (gateEnabled() && !(await verifyGateToken(request.cookies.get(GATE_COOKIE)?.value))) {
    const url = request.nextUrl.clone();
    url.pathname = GATE_PATH;
    // Remember where they were headed, so accepting takes them there and not to the front page.
    url.search = `?next=${encodeURIComponent(request.nextUrl.pathname)}`;
    return NextResponse.redirect(url);
  }
  return intl(request);
}

export const config = {
  matcher: ["/((?!api|gate|_next|_vercel|.*\\..*).*)"],
};
