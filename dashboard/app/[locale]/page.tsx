import { getTranslations, setRequestLocale } from "next-intl/server";

type Status = "ok" | "degraded" | "down";
type Dependency = { name: string; status: Status; latency_ms?: number | null };
type Health = { status: Status; dependencies: Dependency[] };

const API_BASE = process.env.PLEXUS_API_URL ?? "http://localhost:8000";

async function fetchHealth(): Promise<Health | null> {
  try {
    const res = await fetch(`${API_BASE}/v1/health`, { cache: "no-store" });
    return (await res.json()) as Health;
  } catch {
    return null;
  }
}

export default async function OverviewPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("overview");
  const health = await fetchHealth();

  return (
    <>
      <h1>{t("title")}</h1>
      <p className="muted">{t("subtitle")}</p>
      <dl className="grid">
        <div>
          <dt>{t("apiStatus")}</dt>
          <dd className={health ? `status-${health.status}` : "status-down"}>
            {health ? t(`status.${health.status}`) : t("status.unreachable")}
          </dd>
        </div>
        {health?.dependencies.map((d) => (
          <div key={d.name}>
            <dt>{d.name}</dt>
            <dd className={`status-${d.status}`}>{t(`status.${d.status}`)}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}
