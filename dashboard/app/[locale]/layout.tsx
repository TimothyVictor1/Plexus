import type { ReactNode } from "react";
import { Plus_Jakarta_Sans } from "next/font/google";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { routing } from "@/i18n/routing";
import AppShell from "@/components/shell/AppShell";
import "../globals.css";

const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-jakarta",
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
  };

  return (
    <html lang={locale} className={jakarta.variable}>
      <body>
        <NextIntlClientProvider>
          <AppShell locale={locale} labels={labels}>{children}</AppShell>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
