"use client";
// Reviewer console shell: key + name gate (kept in this tab's sessionStorage) and the tab bar.
import Link from "next/link";
import { ReactNode, useEffect, useState } from "react";

import { ErrorBox } from "@/components/ui";
import { getOpsAuth, ops, setOpsAuth } from "@/lib/opsApi";

const TABS = [["declarations", "/ops", "聲明審核"], ["claims", "/ops/claims", "認領與驗證"], ["reports", "/ops/reports", "使用者回報"], ["incidents", "/ops/incidents", "事故"]] as const;

export function OpsShell({ active, children }: { active: string; children: ReactNode }) {
  const [auth, setAuth] = useState<{ key: string; user: string } | null | undefined>(undefined);
  const [key, setKey] = useState("");
  const [user, setUser] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { setAuth(getOpsAuth()); }, []);

  async function login() {
    setError(null);
    setOpsAuth({ key, user: user.trim() });
    try { await ops("/declarations"); setAuth({ key, user: user.trim() }); }
    catch (e) { setOpsAuth(null); setError(e instanceof Error ? e.message : String(e)); }
  }

  if (auth === undefined) return null;
  if (!auth) {
    return (
      <div>
        <h1>揪呷 · 審核後台</h1>
        <div className="card">
          <p className="muted">這是試辦等級的存取控制：一把共用金鑰，姓名由您自己填，會記錄在稽核紀錄裡。</p>
          <label htmlFor="k">金鑰（OPS_API_KEY）</label><input id="k" type="password" value={key} onChange={(e) => setKey(e.target.value)} />
          <label htmlFor="u">您的姓名</label><input id="u" value={user} onChange={(e) => setUser(e.target.value)} />
        </div>
        <ErrorBox message={error} />
        <button className="primary" style={{ width: "100%" }} disabled={!key || user.trim().length < 2} onClick={login}>登入</button>
      </div>
    );
  }
  return (
    <div className="ops-wrap">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <h1>審核後台</h1>
        <span className="muted">{auth.user} · <a href="#" onClick={(e) => { e.preventDefault(); setOpsAuth(null); setAuth(null); }}>登出</a></span>
      </div>
      <div className="tabs">{TABS.map(([k, href, label]) => <Link key={k} href={href} className={active === k ? "on" : ""}>{label}</Link>)}</div>
      {children}
    </div>
  );
}
