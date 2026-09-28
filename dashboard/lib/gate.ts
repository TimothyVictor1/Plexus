/** The shared-link gate: a confidentiality notice and a password, checked on the server.
 *
 *  This is a prototype shared by sending someone a link, so the whole product sits behind one
 *  password rather than real accounts. The password is read from the environment and compared
 *  in middleware; it is never part of the bundle, because anything the browser is given can be
 *  read by whoever holds it.
 *
 *  What a visitor gets instead is a signed cookie saying only that someone entered the right
 *  password and accepted the notice, and when that expires. It carries no identity, so it
 *  proves nothing about who they are — which is all this is meant to do.
 */

export const GATE_COOKIE = "plexus_access";
export const GATE_PATH = "/gate";
const LIFETIME_MS = 7 * 24 * 60 * 60 * 1000;

/** No password configured means no gate. A prototype run locally should not need one. */
export function gateEnabled(): boolean {
  return Boolean(process.env.PLEXUS_ACCESS_PASSWORD);
}

/** What the cookie is signed with. Separate from the password when set, so that changing the
 *  password does not have to invalidate every cookie, and vice versa. */
function signingSecret(): string {
  return process.env.PLEXUS_GATE_SECRET || process.env.PLEXUS_ACCESS_PASSWORD || "";
}

function toBase64Url(bytes: ArrayBuffer): string {
  let binary = "";
  for (const byte of new Uint8Array(bytes)) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function sign(payload: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(signingSecret()),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return toBase64Url(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(payload)));
}

/** Compare without giving away, through how long it takes, how much of it matched. */
export function sameSecret(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let different = 0;
  for (let i = 0; i < a.length; i++) different |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return different === 0;
}

export async function issueGateToken(): Promise<{ value: string; maxAge: number }> {
  const expires = String(Date.now() + LIFETIME_MS);
  return { value: `${expires}.${await sign(expires)}`, maxAge: Math.floor(LIFETIME_MS / 1000) };
}

export async function verifyGateToken(token: string | undefined): Promise<boolean> {
  if (!token) return false;
  const dot = token.lastIndexOf(".");
  if (dot <= 0) return false;
  const expires = token.slice(0, dot);
  const signature = token.slice(dot + 1);
  if (!/^\d+$/.test(expires) || Number(expires) < Date.now()) return false;
  return sameSecret(signature, await sign(expires));
}

export function passwordMatches(submitted: string): boolean {
  const expected = process.env.PLEXUS_ACCESS_PASSWORD ?? "";
  if (!expected) return false;
  return sameSecret(submitted, expected);
}
