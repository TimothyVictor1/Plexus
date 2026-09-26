"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { currentRole, get, setRole, type Overview, type Role } from "@/lib/api";

type Labels = Record<string, string>;

const ROLES: Role[] = ["viewer", "operator", "approver", "admin"];

export default function Nav({ locale, labels }: { locale: string; labels: Labels }) {
  const pathname = usePathname();
  const [pending, setPending] = useState<number | null>(null);
  const [role, setRoleState] = useState<Role>("approver");

  useEffect(() => {
    setRoleState(currentRole());
    get<Overview>("/overview")
      .then((o) => setPending(o.pending_actions))
      .catch(() => setPending(null));
  }, [pathname]);

  const base = `/${locale}`;
  const operate = [
    { href: base, label: labels.overview },
    { href: `${base}/processes`, label: labels.processes },
    { href: `${base}/inbox`, label: labels.inbox, count: pending ?? undefined },
  ];
  const inspect = [
    { href: `${base}/graph`, label: labels.graph },
    { href: `${base}/ledger`, label: labels.ledger },
    { href: `${base}/boundary`, label: labels.boundary },
    { href: `${base}/adapters`, label: labels.adapters },
  ];

  const item = (l: { href: string; label: string; count?: number }) => (
    <Link
      key={l.href}
      href={l.href}
      className="navlink"
      aria-current={pathname === l.href ? "page" : undefined}
    >
      <span>{l.label}</span>
      {l.count !== undefined && l.count > 0 && <span className="cnt">{l.count}</span>}
    </Link>
  );

  return (
    <nav className="nav">
      <div className="brand">
        <span className="bn">Plexus</span>
        <span className="bt">Nordvik Konsult AB</span>
      </div>

      <span className="navsec">{labels.operate}</span>
      {operate.map(item)}
      <span className="navsec">{labels.inspect}</span>
      {inspect.map(item)}

      <div className="navfoot">
        <label className="fl" htmlFor="role">{labels.actingAs}</label>
        <select
          id="role"
          value={role}
          onChange={(e) => {
            const next = e.target.value as Role;
            setRole(next);
            setRoleState(next);
            window.location.reload();
          }}
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>{r}</option>
          ))}
        </select>
        <span>{labels.tenant}: nordvik</span>
        <Link href={locale === "sv" ? "/en" : "/sv"}>{locale === "sv" ? "English" : "Svenska"}</Link>
      </div>
    </nav>
  );
}
