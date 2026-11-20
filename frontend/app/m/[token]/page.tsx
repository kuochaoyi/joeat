"use client";
// Merchant form (opened from the invitation link). Plain-language questions, "not sure" is always a fine answer, nothing is evidence until a reviewer publishes it.
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ErrorBox } from "@/components/ui";
import {
  DeclItem, Declaration, FormItem, FormSpec, MerchantMe, Preview, mFormSpec, mMe, mPreview, mSaveItems, mSaveMenu, mStart, mSubmit,
} from "@/lib/merchantApi";

const EFFECT_TEXT = { confirmed: "已確認", possible: "可能", contains: "含有" } as const;

function Question({ item, value, onChange }: { item: FormItem; value: DeclItem; onChange: (v: DeclItem) => void }) {
  const askCross = item.cross_contact && value.answer === item.cross_contact.asked_when;
  return (
    <div className="q" data-testid={`q-${item.attribute_code}`}>
      <h3>{item.question}</h3>
      <div className="opts" role="radiogroup" aria-label={item.name}>
        {item.answers.map((a) => (
          <button key={a.value} type="button" role="radio" aria-checked={value.answer === a.value} className={value.answer === a.value ? "on" : ""}
                  onClick={() => onChange({ ...value, answer: a.value })}>{a.label}</button>
        ))}
      </div>
      {askCross && item.cross_contact && (
        <div className="sub">
          <p>{item.cross_contact.question}</p>
          <div className="opts" role="radiogroup" aria-label={`${item.name} 共用設備`}>
            {item.cross_contact.options.map((o) => (
              <button key={o.value} type="button" role="radio" aria-checked={value.cross_contact_status === o.value} className={value.cross_contact_status === o.value ? "on" : ""}
                      onClick={() => onChange({ ...value, cross_contact_status: o.value })}>{o.label}</button>
            ))}
          </div>
        </div>
      )}
      {item.certificate && value.answer === "offered" && (
        <input type="text" placeholder="認證編號（選填；有編號才可能列為「已確認」）" value={value.certificate_ref ?? ""} onChange={(e) => onChange({ ...value, certificate_ref: e.target.value || null })} />
      )}
      {value.answer !== "not_sure" && (
        <input type="text" placeholder="備註（選填）" maxLength={300} value={value.note ?? ""} onChange={(e) => onChange({ ...value, note: e.target.value || null })} />
      )}
    </div>
  );
}

export default function MerchantPage() {
  const { token } = useParams<{ token: string }>();
  const [spec, setSpec] = useState<FormSpec | null>(null);
  const [me, setMe] = useState<MerchantMe | null>(null);
  const [decl, setDecl] = useState<Declaration | null>(null);
  const [items, setItems] = useState<Record<string, DeclItem>>({});
  const [menuUrl, setMenuUrl] = useState("");
  const [menuDate, setMenuDate] = useState("");
  const [role, setRole] = useState("owner");
  const [accepted, setAccepted] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<"idle" | "saving" | "saved">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const [s, m] = await Promise.all([mFormSpec(), mMe(token)]);
      setSpec(s); setMe(m); setRole(m.claimant_role || "owner");
      if (m.declaration) adopt(m.declaration);
    } catch (e) { setFatal(e instanceof Error ? e.message : String(e)); }
  }, [token]);
  useEffect(() => { load(); setMenuDate(new Date().toISOString().slice(0, 10)); }, [load]);

  function adopt(d: Declaration) {
    setDecl(d);
    setItems(Object.fromEntries(d.items.map((i) => [i.attribute_code, i])));
    setMenuUrl(d.menu_url ?? "");
    if (d.menu_as_of) setMenuDate(d.menu_as_of);
  }

  // autosave (debounced) while the declaration is editable
  const change = (v: DeclItem) => {
    setItems((cur) => {
      const next = { ...cur, [v.attribute_code]: v };
      if (timer.current) clearTimeout(timer.current);
      setSaved("saving");
      timer.current = setTimeout(async () => {
        try { await mSaveItems(token, Object.values(next)); setSaved("saved"); } catch (e) { setError(e instanceof Error ? e.message : String(e)); setSaved("idle"); }
      }, 600);
      return next;
    });
    setPreview(null);
  };

  async function start() {
    setBusy(true); setError(null);
    try { adopt(await mStart(token)); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }
  async function showPreview() {
    setError(null);
    try {
      if (timer.current) { clearTimeout(timer.current); await mSaveItems(token, Object.values(items)); }
      await mSaveMenu(token, menuUrl.trim() || null);
      setPreview(await mPreview(token));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  async function submit() {
    if (!spec) return;
    setBusy(true); setError(null);
    try {
      if (timer.current) clearTimeout(timer.current);
      await mSaveItems(token, Object.values(items));
      await mSaveMenu(token, menuUrl.trim() || null);
      adopt(await mSubmit(token, { role, menu_as_of: menuDate, accepted, attestation_version: spec.attestation.version }));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    setBusy(false);
  }

  const answered = useMemo(() => Object.values(items).filter((i) => i.answer !== "not_sure").length, [items]);
  const attestation = spec ? spec.attestation.template.replace("{role}", { owner: "老闆", manager: "店長", staff: "員工" }[role] ?? role).replace("{menu_as_of}", menuDate) : "";

  if (fatal) return <div><h1>揪呷 · 店家資料</h1><ErrorBox message={fatal} /></div>;
  if (!spec || !me) return <div><h1>載入中…</h1></div>;

  return (
    <div>
      <h1>{me.restaurant.name}</h1>
      <p className="muted">{me.restaurant.address ?? "地址未知"}{me.restaurant.phone ? ` · ${me.restaurant.phone}` : ""}</p>
      {me.demo && <div className="demo-banner" data-testid="demo-banner">示範資料：這是假的商家與假的聲明，只用於開發與展示。</div>}
      <ErrorBox message={error} />

      {!me.can_declare && <div className="card" data-testid="waiting"><h2 style={{ marginTop: 0 }}>等待身分確認</h2><p>{me.message}</p></div>}

      {me.can_declare && !decl && (
        <div className="card">
          <h2 style={{ marginTop: 0 }}>讓顧客知道您的菜單</h2>
          <p>{spec.intro}</p>
          <p className="muted">您的回答會經過揪呷團隊審核後才會顯示給顧客，並有效 {spec.validity_days} 天。</p>
          <button className="primary" style={{ width: "100%" }} disabled={busy} onClick={start}>{busy ? "準備中…" : "開始填寫"}</button>
        </div>
      )}

      {decl && decl.status === "submitted" && (
        <div className="card" data-testid="submitted"><h2 style={{ marginTop: 0 }}>已送出，等待審核</h2><p>我們會審核後與您聯絡。審核通過後，顧客才會看到您的聲明。</p></div>
      )}
      {decl && decl.status === "approved" && (
        <div className="card" data-testid="approved"><h2 style={{ marginTop: 0 }}>已通過審核</h2><p>您的聲明自發布日起有效 {decl.valid_days} 天；菜單有變動時請聯絡我們更新或撤下。</p></div>
      )}
      {decl && decl.status === "needs_info" && decl.review_note && (
        <div className="error" data-testid="needs-info"><b>審核人員請您補充：</b>{decl.review_note}</div>
      )}

      {decl && decl.editable && (
        <>
          <p className="muted">{spec.intro}</p>
          <div className="legal-banner">{spec.legal_review.note}</div>
          {spec.sections.map((sec) => (
            <section key={sec.key}>
              <h2>{sec.title}</h2>
              {sec.items.map((it) => (
                <Question key={it.attribute_code} item={it} value={items[it.attribute_code] ?? { attribute_code: it.attribute_code, answer: "not_sure", cross_contact_status: "unknown", note: null, certificate_ref: null }} onChange={change} />
              ))}
            </section>
          ))}

          <h2>菜單</h2>
          <div className="card">
            <label htmlFor="menu">菜單連結（選填；附上可以讓審核更快）</label>
            <input id="menu" type="text" inputMode="url" placeholder="https://" value={menuUrl} onChange={(e) => { setMenuUrl(e.target.value); setPreview(null); }} />
            <label htmlFor="mdate">這份回答對應的菜單日期</label>
            <input id="mdate" type="date" value={menuDate} onChange={(e) => setMenuDate(e.target.value)} />
          </div>

          <h2>顧客會看到什麼</h2>
          <button style={{ width: "100%" }} onClick={showPreview}>預覽（已回答 {answered} 題）</button>
          {preview && (
            <div className="card" data-testid="preview">
              {preview.lines.length === 0 && <p>目前沒有任何已回答的項目，顧客會看到「資訊不足」。</p>}
              <ul className="plain">
                {preview.lines.map((l) => <li key={l.attribute_code}><span className={`effect ${l.effect}`}>{EFFECT_TEXT[l.effect]}</span>{l.text}</li>)}
              </ul>
              <p className="muted">{preview.unanswered_note}</p>
              <p className="muted">{preview.verification_note}</p>
            </div>
          )}

          <h2>切結與送出</h2>
          <div className="card">
            <label htmlFor="role">我的身分</label>
            <select id="role" value={role} onChange={(e) => setRole(e.target.value)}><option value="owner">老闆</option><option value="manager">店長</option><option value="staff">員工</option></select>
            <p style={{ marginTop: 12 }}>{attestation}</p>
            <label style={{ display: "flex", gap: 8, alignItems: "flex-start", fontWeight: 400 }}>
              <input type="checkbox" style={{ width: "auto", marginTop: 4 }} checked={accepted} onChange={(e) => setAccepted(e.target.checked)} />
              <span>我已閱讀並同意上述內容</span>
            </label>
          </div>
          <div className="bar"><div className="inner">
            <span className="muted" style={{ alignSelf: "center" }}>{saved === "saving" ? "儲存中…" : saved === "saved" ? "已自動儲存 ✓" : ""}</span>
            <button className="primary" disabled={busy || !accepted || !menuDate} onClick={submit}>{busy ? "送出中…" : "送出審核"}</button>
          </div></div>
        </>
      )}
    </div>
  );
}
