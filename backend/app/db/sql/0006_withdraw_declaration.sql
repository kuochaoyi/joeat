-- 0006: take a published declaration down (the merchant changed the menu, asked us to remove it, or we lost trust in it).
-- Same principle as the kill switch: POSITIVE claims (an "avoid" attribute declared absent / a "require" attribute declared present) stop counting at once;
-- RISK claims (an "avoid" attribute declared present) stay until they expire, because removing them would make users LESS careful.
-- The declaration row is kept (history), its status becomes 'withdrawn', and the merchant may start a new declaration.
CREATE FUNCTION merchant.withdraw_declaration(p_declaration BIGINT, p_actor TEXT, p_note TEXT) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE d merchant.declaration%ROWTYPE; v_retired INT; v_kept INT;
BEGIN
  IF p_actor IS NULL OR btrim(p_actor) = '' THEN RAISE EXCEPTION 'a named reviewer is required' USING ERRCODE = 'check_violation'; END IF;
  IF p_note IS NULL OR length(btrim(p_note)) < 5 THEN RAISE EXCEPTION 'a reason of at least 5 characters is required' USING ERRCODE = 'check_violation'; END IF;
  SELECT * INTO d FROM merchant.declaration WHERE declaration_id = p_declaration FOR UPDATE;
  IF NOT FOUND OR d.status <> 'approved' THEN RAISE EXCEPTION 'only an approved declaration can be withdrawn (status: %)', COALESCE(d.status, 'missing') USING ERRCODE = 'check_violation'; END IF;
  PERFORM set_config('joeat.actor', p_actor, true);

  WITH retired AS (
    UPDATE enrichment.restaurant_attribute_evidence e SET status = 'superseded'
      FROM ref.attribute a
     WHERE a.attribute_code = e.attribute_code AND e.declaration_id = p_declaration AND e.status IN ('active', 'suspended')
       AND ((a.attribute_type = 'avoid' AND e.state IN ('CONFIRMED_ABSENT', 'LIKELY_ABSENT')) OR (a.attribute_type = 'require' AND e.state IN ('CONFIRMED_PRESENT', 'LIKELY_PRESENT')))
    RETURNING 1)
  SELECT count(*) INTO v_retired FROM retired;
  SELECT count(*) INTO v_kept FROM enrichment.restaurant_attribute_evidence WHERE declaration_id = p_declaration AND status = 'active';

  UPDATE merchant.declaration SET status = 'withdrawn' WHERE declaration_id = p_declaration;
  INSERT INTO merchant.declaration_audit (declaration_id, event, actor, detail)
  VALUES (p_declaration, 'withdrawn', p_actor, jsonb_build_object('note', p_note, 'positive_claims_retired', v_retired, 'risk_claims_kept_until_expiry', v_kept));
  RETURN v_retired;
END $$;
