import type { ReactNode } from "react";
import { Inter } from "next/font/google";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import AppShell from "@/components/shell/AppShell";
import "../globals.css";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-inter",
});

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
  const t = await getTranslations("shell");

  const labels: Record<string, string> = {
    mainNav: t("mainNav"),
    home: t("home"),
    ask: t("ask"),
    askPlexus: t("askPlexus"),
    work: t("work"),
    review: t("review"),
    twin: t("twin"),
    connections: t("connections"),
    settings: t("settings"),
    waitingCount: t.raw("waitingCount") as string,
    exampleData: t("exampleData"),
    inviteTeam: t("inviteTeam"),
    accountMenu: t("accountMenu"),
    actingAs: t("actingAs"),
    roleNote: t("roleNote"),
    role_viewer: t("role.viewer"),
    role_operator: t("role.operator"),
    role_approver: t("role.approver"),
    role_admin: t("role.admin"),
    loadingOrg: t("loadingOrg"),
    offlineTitle: t("offlineTitle"),
    offlineBody: t("offlineBody"),
    previewTitle: t("previewTitle"),
    previewBody: t("previewBody"),
  };

  return (
    <html lang={locale} className={inter.variable}>
      <head>
        {/* The display face for headings, the same one the landing page uses, so the two
            read as one product. It is served from a CDN because it is not ours to ship. */}
        <link
          href="https://db.onlinewebfonts.com/c/8cb707a9b8a73f8a7403336b861c3074?family=BubbledotICG-FinePos"
          rel="stylesheet"
        />
      </head>
      <body>
        <NextIntlClientProvider>
          <AppShell locale={locale} labels={labels}>{children}</AppShell>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
