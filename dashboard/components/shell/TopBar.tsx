"use client";

import { useEffect, useRef, useState } from "react";
import { currentRole, setRole, type Role } from "@/lib/api";

const ROLES: Role[] = ["viewer", "operator", "approver", "admin"];

export default function TopBar({
  orgName, isDemo, labels,
}: { orgName: string; isDemo: boolean; labels: Record<string, string> }) {
  const [open, setOpen] = useState(false);
  const [role, setRoleState] = useState<Role>("approver");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => setRoleState(currentRole()), []);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const initial = (orgName || "?").trim().charAt(0).toUpperCase();

  return (
    <header className="topbar">
      <div className="org">
        <span className="org-name">{orgName}</span>
        {isDemo && <span className="badge-demo">{labels.exampleData}</span>}
      </div>

      <div className="row" style={{ gap: 10 }}>
        <button className="btn secondary sm" style={{ minHeight: 40 }}>{labels.inviteTeam}</button>
        <div ref={menuRef} style={{ position: "relative" }}>
          <button
            className="avatar"
            aria-label={labels.accountMenu}
            aria-expanded={open}
            aria-haspopup="menu"
            onClick={() => setOpen((v) => !v)}
          >
            {initial}
          </button>
          {open && (
            <div
              role="menu"
              style={{
                position: "absolute", right: 0, top: 44, zIndex: 20, minWidth: 220,
                background: "var(--card)", border: "1px solid var(--line-2)",
                borderRadius: "var(--radius-ctl)", padding: 14,
                display: "flex", flexDirection: "column", gap: 8,
                boxShadow: "0 12px 32px -18px rgba(0,0,0,.9)",
              }}
            >
              <label htmlFor="role-select" className="small muted">{labels.actingAs}</label>
              <select
                id="role-select"
                className="select"
                value={role}
                onChange={(e) => {
                  const next = e.target.value as Role;
                  setRole(next);
                  setRoleState(next);
                  window.location.reload();
                }}
              >
                {ROLES.map((r) => <option key={r} value={r}>{labels[`role_${r}`] ?? r}</option>)}
              </select>
              <p className="small muted" style={{ lineHeight: 1.45 }}>{labels.roleNote}</p>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
