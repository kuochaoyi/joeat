-- 0004 publish_declaration, restored when 0007 is downgraded
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

