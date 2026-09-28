import { NextResponse } from "next/server";

import { GATE_COOKIE, issueGateToken, passwordMatches } from "@/lib/gate";

/** Check the password on the server and hand back a signed cookie.
 *
 *  The password itself never leaves this process: the browser sends an attempt and is told only
 *  whether it was right. A wrong attempt says so in the plainest terms, because there is one
 *  password and no accounts, so there is nothing to give away by admitting it was wrong.
 */
export async function POST(request: Request): Promise<NextResponse> {
  let password = "";
  let accepted = false;
  try {
    const body = (await request.json()) as { password?: unknown; accepted?: unknown };
    password = typeof body.password === "string" ? body.password : "";
    accepted = body.accepted === true;
  } catch {
    return NextResponse.json({ ok: false, reason: "malformed" }, { status: 400 });
  }

  if (!accepted) return NextResponse.json({ ok: false, reason: "not_accepted" }, { status: 400 });
  if (!passwordMatches(password)) {
    return NextResponse.json({ ok: false, reason: "wrong_password" }, { status: 401 });
  }

  const token = await issueGateToken();
  const response = NextResponse.json({ ok: true });
  response.cookies.set(GATE_COOKIE, token.value, {
    httpOnly: true, // script on the page cannot read it, so a bug on a screen cannot leak it
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: token.maxAge,
  });
  return response;
}
