"use client";
// 審核後台：管理員帳號管理（/ops/admins）— 方案 A（瀏覽器本機名冊，不更動資料庫）
import { ShieldCheck, UserCheck, UserPlus, UserX } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";

import { OpsShell } from "@/components/OpsShell";
import { ErrorBox, GameButton } from "@/components/ui";
import {
  addLocalAdmin,
  getLocalAdmins,
  getOpsAuth,
  type LocalAdminRecord,
  toggleLocalAdmin,
} from "@/lib/opsApi";

function AdminsManager() {
  const [admins, setAdmins] = useState<LocalAdminRecord[]>([]);
  const [currentUser, setCurrentUser] = useState<string>("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("審核員");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAdmins(getLocalAdmins());
    setCurrentUser(getOpsAuth()?.user ?? "");
  }, []);

  function handleAdd(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (name.trim().length < 2) {
      setError("管理員姓名至少需要 2 個字。");
      return;
    }
    try {
      setAdmins(addLocalAdmin(name, role));
      setName("");
      setRole("審核員");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  function handleToggle(record: LocalAdminRecord) {
    setError(null);
    if (record.active && record.name.trim().toLowerCase() === currentUser.trim().toLowerCase()) {
      setError("無法停用目前正在操作中的本人帳號。");
      return;
    }
    setAdmins(toggleLocalAdmin(record.id));
  }

  return (
    <div className="space-y-5">
      {/* 驗證模式說明 */}
      <div className="flex items-start gap-3 rounded-3xl border-2 border-line bg-surface p-5 shadow-card">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-brand-soft text-brand">
          <ShieldCheck className="h-5 w-5" aria-hidden="true" />
        </span>
        <div className="space-y-1">
          <h2 className="m-0 text-base font-black text-ink">目前驗證模式：共用金鑰（OPS_API_KEY）＋ 稽核姓名</h2>
          <p className="m-0 text-xs leading-relaxed text-muted">
            目前操作者為 <b className="text-ink">{currentUser || "—"}</b>。本頁名冊儲存在此瀏覽器本機（不更動資料庫）：啟用中的管理員會顯示在登入頁供快速點選，已停用的管理員將被阻擋由此裝置登入。
          </p>
        </div>
      </div>

      <ErrorBox message={error} />

      {/* 新增管理員表單 */}
      <form
        onSubmit={handleAdd}
        className="rounded-3xl border-2 border-line bg-surface p-5 shadow-card"
      >
        <h3 className="m-0 mb-3 flex items-center gap-2 text-base font-black text-ink">
          <UserPlus className="h-4 w-4 text-brand" aria-hidden="true" />
          新增管理員至名冊
        </h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <label htmlFor="admin-name" className="mb-1 block text-xs font-extrabold text-muted">
              管理員姓名（至少 2 字）
            </label>
            <input
              id="admin-name"
              type="text"
              required
              minLength={2}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：審核員小美"
              className="h-11 w-full rounded-2xl border-2 border-line bg-bg px-3 text-sm font-semibold text-ink focus:border-brand focus:bg-surface focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="admin-role" className="mb-1 block text-xs font-extrabold text-muted">
              職稱／角色備註
            </label>
            <input
              id="admin-role"
              type="text"
              value={role}
              onChange={(e) => setRole(e.target.value)}
              placeholder="例如：主審、營運專員"
              className="h-11 w-full rounded-2xl border-2 border-line bg-bg px-3 text-sm font-semibold text-ink focus:border-brand focus:bg-surface focus:outline-none"
            />
          </div>
          <div className="flex items-end">
            <GameButton type="submit" variant="primary" size="sm" className="h-11 w-full">
              新增管理員
            </GameButton>
          </div>
        </div>
      </form>

      {/* 管理員名冊表格 */}
      <div className="overflow-x-auto rounded-3xl border-2 border-line bg-surface p-5 shadow-card">
        <h3 className="m-0 mb-3 text-base font-black text-ink">管理員名冊（共 {admins.length} 位）</h3>
        <table className="ops" data-testid="admins-table">
          <thead>
            <tr>
              <th>姓名</th>
              <th>角色</th>
              <th>狀態</th>
              <th>建立時間</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {admins.map((a) => {
              const isSelf = a.name.trim().toLowerCase() === currentUser.trim().toLowerCase();
              return (
                <tr key={a.id}>
                  <td className="font-bold text-ink">
                    {a.name}{" "}
                    {isSelf && (
                      <span className="rounded-full bg-brand-soft px-2 py-0.5 text-[0.7rem] font-extrabold text-brand">
                        目前登入
                      </span>
                    )}
                  </td>
                  <td>{a.role}</td>
                  <td>
                    {a.active ? (
                      <span className="inline-flex items-center gap-1 rounded-full bg-ok-soft px-2.5 py-0.5 text-xs font-bold text-ok">
                        <UserCheck className="h-3.5 w-3.5" aria-hidden="true" />
                        啟用中
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full bg-crit-soft px-2.5 py-0.5 text-xs font-bold text-crit">
                        <UserX className="h-3.5 w-3.5" aria-hidden="true" />
                        已停用
                      </span>
                    )}
                  </td>
                  <td className="text-muted">{new Date(a.createdAt).toLocaleString("zh-TW")}</td>
                  <td>
                    <button
                      type="button"
                      disabled={a.active && isSelf}
                      onClick={() => handleToggle(a)}
                      className="rounded-xl border border-line bg-bg px-3 py-1 text-xs font-bold text-ink transition hover:border-brand disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                    >
                      {a.active ? "停用" : "重新啟用"}
                    </button>
                  </td>
                </tr>
              );
            })}
            {admins.length === 0 && (
              <tr>
                <td colSpan={5} className="muted">
                  尚未建立名冊，可在上方新增常用管理員姓名。
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function OpsAdminsPage() {
  return (
    <OpsShell active="admins">
      <AdminsManager />
    </OpsShell>
  );
}
