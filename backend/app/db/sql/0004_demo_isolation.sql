-- 0004_demo_isolation.sql : fake (demo) merchant data must never become real first-party evidence.
--   * merchant.claim.is_demo marks a claim as DEMO. Its declarations publish into the TEST source ('test_fixture', is_test = TRUE),
--     which the recommendation engine ignores unless ALLOW_TEST_EVIDENCE is switched on (never in production).
--   * Demo declarations only compete with / retire demo evidence; real first-party evidence is untouched.
-- The function bodies below are 0003's, with exactly those changes.

ALTER TABLE merchant.claim ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT FALSE;

-- What publishing WOULD write, and what it would contradict. Used by both the reviewer's preview and publish_declaration (one source of truth).
--   state:  strong claim -> CONFIRMED_*, basic claim -> LIKELY_*; halal "offered" needs a certificate reference to be confirmed
--   cross contact (critical allergens only, "absent_entire_menu"): confirmed_none keeps the state; possible/unknown cap it at LIKELY_ABSENT
--           (the engine then raises a critical warning, never a safe badge); confirmed_shared turns it into LIKELY_PRESENT (the engine excludes the restaurant)
CREATE OR REPLACE FUNCTION merchant.declaration_plan(p_declaration BIGINT)
RETURNS TABLE (attribute_code TEXT, attribute_type TEXT, answer TEXT, cross_contact_status TEXT, new_state ref.evidence_state, evidence_basis TEXT, confidence TEXT,
               presence_extent TEXT, capped_by_cross_contact BOOLEAN, conflicts BIGINT[], conflicts_confirmed BOOLEAN)
LANGUAGE sql STABLE AS $$
  WITH d AS (
    SELECT dc.restaurant_id, dc.menu_url, dc.menu_file_ref, c.verification_level AS vlevel, c.is_demo AS demo
      FROM merchant.declaration dc JOIN merchant.claim c USING (claim_id) WHERE dc.declaration_id = p_declaration),
  raw AS (
    SELECT i.attribute_code AS attr, a.attribute_type AS atype, a.risk_level, i.answer AS ans, i.cross_contact_status AS cc, i.certificate_ref,
           d.restaurant_id, d.menu_url, d.menu_file_ref, d.vlevel, d.demo,
           (CASE
              WHEN a.attribute_type = 'avoid' AND i.answer = 'absent_entire_menu' THEN CASE WHEN d.vlevel = 'strong' THEN 'CONFIRMED_ABSENT' ELSE 'LIKELY_ABSENT' END
              WHEN a.attribute_type = 'avoid'                                       THEN CASE WHEN d.vlevel = 'strong' THEN 'CONFIRMED_PRESENT' ELSE 'LIKELY_PRESENT' END
              WHEN i.answer = 'offered' THEN CASE WHEN d.vlevel = 'strong' AND (i.attribute_code <> 'halal' OR i.certificate_ref IS NOT NULL) THEN 'CONFIRMED_PRESENT' ELSE 'LIKELY_PRESENT' END
              ELSE CASE WHEN d.vlevel = 'strong' THEN 'CONFIRMED_ABSENT' ELSE 'LIKELY_ABSENT' END
            END) AS s0
      FROM merchant.declaration_item i JOIN ref.attribute a USING (attribute_code) CROSS JOIN d
     WHERE i.declaration_id = p_declaration AND i.answer <> 'not_sure'),
  capped AS (
    SELECT r.*, (CASE WHEN r.atype = 'avoid' AND r.risk_level = 'critical' AND r.ans = 'absent_entire_menu'
                      THEN CASE r.cc WHEN 'confirmed_none' THEN r.s0 WHEN 'confirmed_shared' THEN 'LIKELY_PRESENT' ELSE 'LIKELY_ABSENT' END
                      ELSE r.s0 END)::ref.evidence_state AS st
      FROM raw r)
  SELECT c.attr, c.atype, c.ans, c.cc, c.st,
         CASE WHEN (c.menu_url IS NOT NULL OR c.menu_file_ref IS NOT NULL) AND c.st IN ('CONFIRMED_ABSENT','CONFIRMED_PRESENT','LIKELY_PRESENT') THEN 'official_menu' ELSE 'restaurant_declaration' END,
         CASE WHEN c.st IN ('CONFIRMED_ABSENT','CONFIRMED_PRESENT') THEN 'HIGH' ELSE 'MEDIUM' END,
         CASE c.ans WHEN 'present_in_some_dishes' THEN 'some' WHEN 'present_in_most_dishes' THEN 'most' END,
         (c.st IS DISTINCT FROM c.s0::ref.evidence_state),
         x.ids, COALESCE(x.has_confirmed, FALSE)
    FROM capped c
    LEFT JOIN LATERAL (
      SELECT array_agg(e.evidence_id) AS ids, bool_or(e.state IN ('CONFIRMED_PRESENT','CONFIRMED_ABSENT')) AS has_confirmed
        FROM enrichment.restaurant_attribute_evidence e
       WHERE e.restaurant_id = c.restaurant_id AND e.attribute_code = c.attr AND e.status = 'active'
         AND e.source_id <> (SELECT source_id FROM ref.data_source WHERE source_type = CASE WHEN c.demo THEN 'test_fixture' ELSE 'first_party' END)
         AND (e.valid_until IS NULL OR e.valid_until >= ref.today_tpe())
         AND ((c.st IN ('CONFIRMED_ABSENT','LIKELY_ABSENT') AND e.state IN ('CONFIRMED_PRESENT','LIKELY_PRESENT'))
           OR (c.st IN ('CONFIRMED_PRESENT','LIKELY_PRESENT') AND e.state IN ('CONFIRMED_ABSENT','LIKELY_ABSENT')))
    ) x ON TRUE
$$;

-- Publish = approve + write first-party evidence. Contradictions are never resolved silently:
--   LIKELY_* contradictions block publishing unless the reviewer passes p_supersede (recorded in the audit log); CONFIRMED_* contradictions always block.
CREATE OR REPLACE FUNCTION merchant.publish_declaration(p_declaration BIGINT, p_reviewer TEXT, p_supersede BOOLEAN DEFAULT FALSE) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
  d merchant.declaration%ROWTYPE; c merchant.claim%ROWTYPE; it RECORD; v_src SMALLINT; v_today DATE := ref.today_tpe();
  v_text TEXT; v_new BIGINT; v_n INT := 0;
BEGIN
  IF p_reviewer IS NULL OR btrim(p_reviewer) = '' THEN RAISE EXCEPTION 'a named reviewer is required' USING ERRCODE = 'check_violation'; END IF;
  SELECT * INTO d FROM merchant.declaration WHERE declaration_id = p_declaration FOR UPDATE;
  IF NOT FOUND OR d.status <> 'submitted' THEN RAISE EXCEPTION 'only a submitted declaration can be published (status: %)', COALESCE(d.status, 'missing') USING ERRCODE = 'check_violation'; END IF;
  SELECT * INTO c FROM merchant.claim WHERE claim_id = d.claim_id;
  IF c.status <> 'verified' THEN RAISE EXCEPTION 'claim is % : cannot publish', c.status USING ERRCODE = 'check_violation'; END IF;
  IF c.verification_method = 'official_menu_review' AND d.menu_url IS NULL AND d.menu_file_ref IS NULL THEN
    RAISE EXCEPTION 'verification by official_menu_review needs the menu (menu_url or menu_file_ref) on the declaration' USING ERRCODE = 'check_violation';
  END IF;
  SELECT source_id INTO v_src FROM ref.data_source WHERE source_type = CASE WHEN c.is_demo THEN 'test_fixture' ELSE 'first_party' END;
  PERFORM set_config('joeat.actor', p_reviewer, true);

  FOR it IN SELECT p.*, i.note, i.certificate_ref FROM merchant.declaration_plan(p_declaration) p
            JOIN merchant.declaration_item i ON i.declaration_id = p_declaration AND i.attribute_code = p.attribute_code LOOP
    IF it.conflicts IS NOT NULL THEN
      IF it.conflicts_confirmed THEN
        RAISE EXCEPTION 'contradiction with CONFIRMED evidence % on attribute %: resolve the data or reject the declaration', it.conflicts, it.attribute_code USING ERRCODE = 'check_violation';
      ELSIF NOT p_supersede THEN
        RAISE EXCEPTION 'contradiction with existing evidence % on attribute %: review it, then publish with supersede = true', it.conflicts, it.attribute_code USING ERRCODE = 'check_violation';
      END IF;
    END IF;

    v_text := format('店家聲明（%s；聲明人 %s；驗證 %s／%s／%s；菜單日期 %s）：%s；共用設備：%s%s%s',
                     v_today, d.declared_role, c.verification_method, c.verified_by, c.verified_at::date, d.menu_as_of,
                     CASE it.answer WHEN 'absent_entire_menu' THEN '菜單未使用' WHEN 'present_in_some_dishes' THEN '部分餐點含有' WHEN 'present_in_most_dishes' THEN '大部分餐點含有'
                                    WHEN 'offered' THEN '有提供' WHEN 'not_offered' THEN '未提供' END,
                     CASE it.cross_contact_status WHEN 'confirmed_none' THEN '確認無共用' WHEN 'possible' THEN '可能共用' WHEN 'confirmed_shared' THEN '確認共用' ELSE '未知' END,
                     CASE WHEN it.capped_by_cross_contact THEN '（過敏原在共用設備未確認無共用時，不採「確認不含」）' ELSE '' END,
                     COALESCE('；備註：' || it.note, ''));

    INSERT INTO enrichment.restaurant_attribute_evidence
      (restaurant_id, attribute_code, state, evidence_text, evidence_basis, applies_to, source_id, source_url, confidence, observed_at, last_verified_at, valid_until,
       declaration_id, status, cross_contact_status, presence_extent)
    VALUES (d.restaurant_id, it.attribute_code, it.new_state, v_text, it.evidence_basis, 'this_branch', v_src, d.menu_url, it.confidence, LEAST(d.menu_as_of, v_today), v_today,
            v_today + d.valid_days, p_declaration, 'active', it.cross_contact_status, it.presence_extent)
    ON CONFLICT ON CONSTRAINT evidence_unique DO UPDATE SET state = EXCLUDED.state, evidence_text = EXCLUDED.evidence_text, source_url = EXCLUDED.source_url,
      confidence = EXCLUDED.confidence, observed_at = EXCLUDED.observed_at, last_verified_at = EXCLUDED.last_verified_at, valid_until = EXCLUDED.valid_until,
      declaration_id = EXCLUDED.declaration_id, status = 'active', superseded_by = NULL, suspended_by_incident = NULL,
      cross_contact_status = EXCLUDED.cross_contact_status, presence_extent = EXCLUDED.presence_extent
    RETURNING evidence_id INTO v_new;
    v_n := v_n + 1;

    IF it.conflicts IS NOT NULL THEN
      UPDATE enrichment.restaurant_attribute_evidence SET status = 'superseded', superseded_by = v_new WHERE evidence_id = ANY (it.conflicts);
      INSERT INTO merchant.declaration_audit (declaration_id, event, actor, detail)
      VALUES (p_declaration, 'superseded_third_party_evidence', p_reviewer, jsonb_build_object('attribute', it.attribute_code, 'superseded', it.conflicts, 'by', v_new));
    END IF;
  END LOOP;

  -- a new declaration replaces the previous one: first-party evidence it did not re-assert (including attributes now "not sure") is retired
  UPDATE enrichment.restaurant_attribute_evidence SET status = 'superseded'
   WHERE restaurant_id = d.restaurant_id AND source_id = v_src AND status = 'active' AND declaration_id IS DISTINCT FROM p_declaration;

  UPDATE merchant.declaration SET status = 'approved', reviewed_by = p_reviewer, reviewed_at = now() WHERE declaration_id = p_declaration;
  RETURN v_n;
END $$;

