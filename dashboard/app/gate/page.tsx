import { routing } from "@/i18n/routing";

import GateForm from "./GateForm";

/** The notice and the password, outside the locale layout.
 *
 *  Deliberately not under app/[locale]: that layout builds the whole console shell and loads
 *  the organisation, and none of that should happen for someone who has not been let in yet.
 *  Messages are read straight from the same translation files the rest of the console uses, so
 *  the notice is written once per language and nowhere else.
 */
export const metadata = { title: "Plexus" };

type Messages = {
  gate: {
    title: string;
    lead: string;
    terms: string[];
    accept: string;
    passwordLabel: string;
    passwordPlaceholder: string;
    submit: string;
    working: string;
    wrongPassword: string;
    mustAccept: string;
    failed: string;
    footer: string;
  };
};

export default async function GatePage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string; locale?: string }>;
}) {
  const { next, locale: asked } = await searchParams;
  const locale = routing.locales.includes(asked as (typeof routing.locales)[number])
    ? (asked as string)
    : routing.defaultLocale;
  const messages = ((await import(`@/messages/${locale}.json`)) as { default: Messages }).default;

  // Only ever send them somewhere inside this console, never to an address someone put in a link.
  const destination = next && next.startsWith("/") && !next.startsWith("//") ? next : `/${locale}`;

  return (
    <GateForm
      t={messages.gate}
      next={destination}
      locale={locale}
      otherLocale={locale === "sv" ? "en" : "sv"}
    />
  );
}
