import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import Nav from "@/components/Nav";
import "../globals.css";

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export const metadata = { title: "Plexus" };

export default async function LocaleLayout({
  children,
  params,
}: {
  children: ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);
  const t = await getTranslations("nav");

  const labels = {
    overview: t("overview"),
    processes: t("processes"),
    inbox: t("inbox"),
    graph: t("graph"),
    ledger: t("ledger"),
    boundary: t("boundary"),
    adapters: t("adapters"),
    operate: t("operate"),
    inspect: t("inspect"),
    actingAs: t("actingAs"),
    tenant: t("tenant"),
  };

  return (
    <html lang={locale}>
      <body>
        <NextIntlClientProvider>
          <div className="shell">
            <Nav locale={locale} labels={labels} />
            <div className="main">{children}</div>
          </div>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
