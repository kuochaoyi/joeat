-- 0003_merchant_declaration.sql : merchant self-declaration lifecycle (applied by Alembic revision 0003).
-- Supersedes docs/merchant/draft_0003_merchant_declaration.sql (the validated draft); decisions: docs/decisions/0001-merchant-declaration.md
--
-- Interim rule (until the "recommendation integration" step): the recommendation engine is NOT changed. Everything a declaration can express
-- but the engine cannot use yet (cross_contact_status, presence_extent, safety/preference class) is STORED on the evidence / reference rows, and
-- the state that is published is the conservative one, so the unchanged engine can never show a safer picture than the declaration supports.

CREATE SCHEMA IF NOT EXISTS merchant;

-- ============================================================ 1. safety vs preference (data only; used at integration time)
ALTER TABLE ref.attribute ADD COLUMN default_constraint_class TEXT NOT NULL DEFAULT 'preference' CHECK (default_constraint_class IN ('safety','preference'));
ALTER TABLE ref.constraint_reason ADD COLUMN constraint_class TEXT NOT NULL DEFAULT 'preference' CHECK (constraint_class IN ('safety','preference'));
UPDATE ref.attribute SET default_constraint_class = 'safety' WHERE attribute_code IN ('peanut','tree_nut','shellfish','milk','egg','sesame','soy','gluten','gluten_free');
UPDATE ref.constraint_reason SET constraint_class = 'safety' WHERE reason IN ('allergy','medical','religion');

-- The class belongs to the CONSTRAINT (why this person avoids it), not to the attribute: "no seafood" is safety for a fish allergy and preference for a dislike.
CREATE FUNCTION ref.effective_constraint_class(p_reason TEXT, p_attribute TEXT) RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT CASE WHEN p_reason IS NULL OR p_reason = 'unspecified'
              THEN (SELECT default_constraint_class FROM ref.attribute WHERE attribute_code = p_attribute)
              ELSE (SELECT constraint_class FROM ref.constraint_reason WHERE reason = p_reason) END $$;

-- ============================================================ 2. who may speak for a restaurant
CREATE TABLE merchant.claim (
  claim_id            BIGSERIAL PRIMARY KEY,
  restaurant_id       UUID NOT NULL REFERENCES identity.restaurant,
  token_hash          TEXT NOT NULL UNIQUE,            -- SHA-256 of the invite token; the raw token is shown once and never stored
  status              TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','verified','revoked','expired')),
  verification_method TEXT CHECK (verification_method IN ('phone_callback','onsite_visit','official_menu_review','official_channel_message')),
  verification_level  TEXT NOT NULL DEFAULT 'none' CHECK (verification_level IN ('none','basic','strong')),
  verification_note   TEXT,                            -- what was actually done: who answered the call / what was seen on site / which menu was reviewed
  verified_by         TEXT, verified_at TIMESTAMPTZ,
  claimant_line_ref   TEXT,                             -- hashed
  claimant_role       TEXT CHECK (claimant_role IN ('owner','manager','staff')),
  invited_by          TEXT NOT NULL,
  invited_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at          TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '30 days'),
  CONSTRAINT claim_pair UNIQUE (claim_id, restaurant_id),
  -- who verified, when, how, and on what evidence: all four are mandatory for a verified claim
  CONSTRAINT claim_verified_needs_proof CHECK (status <> 'verified' OR (verification_method IS NOT NULL AND verified_by IS NOT NULL AND verified_at IS NOT NULL
                                                AND verification_level <> 'none' AND length(btrim(coalesce(verification_note, ''))) >= 5)),
  -- the level follows from the method: callback / visit / reviewed menu are strong; a channel message is only basic
  CONSTRAINT claim_level_matches_method CHECK (verification_level = 'none'
                                                OR (verification_level = 'strong' AND verification_method IN ('phone_callback','onsite_visit','official_menu_review'))
                                                OR (verification_level = 'basic'  AND verification_method = 'official_channel_message'))
);
CREATE INDEX claim_restaurant ON merchant.claim (restaurant_id);

-- ============================================================ 3. what they declare
CREATE TABLE merchant.declaration (
  declaration_id   BIGSERIAL PRIMARY KEY,
  claim_id         BIGINT NOT NULL,
  restaurant_id    UUID NOT NULL,
  status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','needs_info','approved','rejected','withdrawn')),
  valid_days       SMALLINT NOT NULL DEFAULT 90 CHECK (valid_days BETWEEN 1 AND 180),
  menu_as_of       DATE,
  menu_url         TEXT, menu_file_ref TEXT,
  declared_role    TEXT CHECK (declared_role IN ('owner','manager','staff')),
  attestation_version TEXT, attested_at TIMESTAMPTZ,
  submitted_at     TIMESTAMPTZ, reviewed_by TEXT, reviewed_at TIMESTAMPTZ, review_note TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT decl_claim_fk FOREIGN KEY (claim_id, restaurant_id) REFERENCES merchant.claim (claim_id, restaurant_id),
  CONSTRAINT decl_submitted_needs_attestation CHECK (status NOT IN ('submitted','approved') OR (attested_at IS NOT NULL AND menu_as_of IS NOT NULL AND declared_role IS NOT NULL)),
  CONSTRAINT decl_reviewed_needs_reviewer CHECK (status NOT IN ('approved','rejected','needs_info') OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
  CONSTRAINT decl_rejection_needs_note CHECK (status NOT IN ('rejected','needs_info') OR length(btrim(coalesce(review_note, ''))) >= 5)
);
CREATE INDEX declaration_restaurant ON merchant.declaration (restaurant_id, status);

CREATE TABLE merchant.declaration_item (
  declaration_id BIGINT NOT NULL REFERENCES merchant.declaration ON DELETE CASCADE,
  attribute_code TEXT NOT NULL REFERENCES ref.attribute,
  answer         TEXT NOT NULL DEFAULT 'not_sure'      -- never defaults to "absent": silence stays UNKNOWN
                 CHECK (answer IN ('absent_entire_menu','present_in_some_dishes','present_in_most_dishes','offered','not_offered','not_sure')),
  -- shared kitchen equipment (fryer, wok, grill, prep surface) for this attribute
  cross_contact_status TEXT NOT NULL DEFAULT 'unknown' CHECK (cross_contact_status IN ('confirmed_none','possible','confirmed_shared','unknown')),
  note           TEXT,
  certificate_ref TEXT,
  PRIMARY KEY (declaration_id, attribute_code)
);

CREATE TABLE merchant.declaration_audit (
  audit_id BIGSERIAL PRIMARY KEY, declaration_id BIGINT NOT NULL REFERENCES merchant.declaration,
  event TEXT NOT NULL, actor TEXT, at TIMESTAMPTZ NOT NULL DEFAULT now(), detail JSONB
);

CREATE TABLE merchant.incident_report (
  incident_id   BIGSERIAL PRIMARY KEY,
  restaurant_id UUID NOT NULL REFERENCES identity.restaurant,
  attribute_code TEXT REFERENCES ref.attribute,
  severity      TEXT NOT NULL CHECK (severity IN ('allergic_reaction','wrong_info','other')),
  reporter_ref  TEXT,
  description   TEXT,
  status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','confirmed','dismissed')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(), handled_by TEXT, handled_at TIMESTAMPTZ,
  CHECK ((status = 'open') = (handled_at IS NULL))
);
CREATE INDEX incident_restaurant ON merchant.incident_report (restaurant_id, status);

-- ============================================================ 4. guards
CREATE FUNCTION merchant.item_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_status text; v_type text;
BEGIN
  SELECT status INTO v_status FROM merchant.declaration WHERE declaration_id = COALESCE(NEW.declaration_id, OLD.declaration_id);
  IF v_status NOT IN ('draft','needs_info') THEN
    RAISE EXCEPTION 'declaration is % : its items are frozen', v_status USING ERRCODE = 'check_violation';
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  SELECT attribute_type INTO v_type FROM ref.attribute WHERE attribute_code = NEW.attribute_code;
  IF v_type = 'avoid' AND NEW.answer NOT IN ('absent_entire_menu','present_in_some_dishes','present_in_most_dishes','not_sure') THEN
    RAISE EXCEPTION 'answer % is not valid for avoid-type attribute %', NEW.answer, NEW.attribute_code USING ERRCODE = 'check_violation';
  END IF;
  IF v_type = 'require' AND NEW.answer NOT IN ('offered','not_offered','not_sure') THEN
    RAISE EXCEPTION 'answer % is not valid for require-type attribute %', NEW.answer, NEW.attribute_code USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER item_guard_trg BEFORE INSERT OR UPDATE OR DELETE ON merchant.declaration_item FOR EACH ROW EXECUTE FUNCTION merchant.item_guard();

CREATE FUNCTION merchant.declaration_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'declarations are never deleted (history is kept); withdraw it instead' USING ERRCODE = 'check_violation';
  END IF;
  IF OLD.status IN ('approved','rejected','withdrawn') AND NEW.status <> OLD.status AND NOT (OLD.status = 'approved' AND NEW.status = 'withdrawn') THEN
    RAISE EXCEPTION 'a % declaration cannot become %', OLD.status, NEW.status USING ERRCODE = 'check_violation';
  END IF;
  IF NEW.status <> OLD.status THEN
    INSERT INTO merchant.declaration_audit (declaration_id, event, actor, detail)
    VALUES (NEW.declaration_id, 'status:' || NEW.status, current_setting('joeat.actor', true), jsonb_build_object('from', OLD.status));
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER declaration_guard_trg BEFORE UPDATE OR DELETE ON merchant.declaration FOR EACH ROW EXECUTE FUNCTION merchant.declaration_guard();

CREATE FUNCTION merchant.declaration_created_audit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO merchant.declaration_audit (declaration_id, event, actor, detail)
  VALUES (NEW.declaration_id, 'status:' || NEW.status, current_setting('joeat.actor', true), jsonb_build_object('claim_id', NEW.claim_id, 'valid_days', NEW.valid_days));
  RETURN NEW;
END $$;
CREATE TRIGGER declaration_created_audit_trg AFTER INSERT ON merchant.declaration FOR EACH ROW EXECUTE FUNCTION merchant.declaration_created_audit();

CREATE FUNCTION merchant.audit_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'declaration_audit is append-only' USING ERRCODE = 'check_violation'; END $$;
CREATE TRIGGER audit_append_only_trg BEFORE UPDATE OR DELETE ON merchant.declaration_audit FOR EACH ROW EXECUTE FUNCTION merchant.audit_append_only();

-- ============================================================ 5. evidence lifecycle
ALTER TABLE enrichment.restaurant_attribute_evidence
  ADD COLUMN status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','suspended')),
  ADD COLUMN superseded_by BIGINT REFERENCES enrichment.restaurant_attribute_evidence (evidence_id),
  ADD COLUMN declaration_id BIGINT REFERENCES merchant.declaration (declaration_id),
  ADD COLUMN suspended_by_incident BIGINT REFERENCES merchant.incident_report (incident_id),
  ADD COLUMN cross_contact_status TEXT CHECK (cross_contact_status IN ('confirmed_none','possible','confirmed_shared','unknown')),   -- NULL = not applicable (third-party evidence)
  ADD COLUMN presence_extent TEXT CHECK (presence_extent IN ('some','most'));                                                          -- NULL = unknown extent: the engine treats it as the whole restaurant
CREATE INDEX evidence_declaration ON enrichment.restaurant_attribute_evidence (declaration_id) WHERE declaration_id IS NOT NULL;

CREATE OR REPLACE VIEW enrichment.v_evidence_valid AS
SELECT e.* FROM enrichment.restaurant_attribute_evidence e
JOIN ref.data_source s USING (source_id)
WHERE e.status = 'active'
  AND (e.valid_until IS NULL OR e.valid_until >= ref.today_tpe())
  AND (NOT s.is_test OR coalesce(current_setting('joeat.allow_test_evidence', true), 'off') = 'on');

-- NOTE: the legal pair (LIKELY_ABSENT, restaurant_declaration) is reference data and lives in data/seed/01_attribute_seed.sql (it references ref.evidence_basis, which is seeded after the migrations).

-- ============================================================ 6. workflow
CREATE FUNCTION merchant.start_declaration(p_claim BIGINT, p_valid_days INT DEFAULT 90) RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE c merchant.claim%ROWTYPE; v_id BIGINT;
BEGIN
  SELECT * INTO c FROM merchant.claim WHERE claim_id = p_claim FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'claim % not found', p_claim; END IF;
  IF c.status <> 'verified' THEN RAISE EXCEPTION 'claim is % : only a verified claim can declare', c.status USING ERRCODE = 'check_violation'; END IF;
  IF c.expires_at < now() THEN RAISE EXCEPTION 'claim expired' USING ERRCODE = 'check_violation'; END IF;
  INSERT INTO merchant.declaration (claim_id, restaurant_id, valid_days) VALUES (c.claim_id, c.restaurant_id, p_valid_days) RETURNING declaration_id INTO v_id;
  INSERT INTO merchant.declaration_item (declaration_id, attribute_code) SELECT v_id, attribute_code FROM ref.attribute WHERE is_active;
  RETURN v_id;
END $$;

CREATE FUNCTION merchant.submit_declaration(p_declaration BIGINT, p_role TEXT, p_menu_as_of DATE, p_attestation_version TEXT) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE d merchant.declaration%ROWTYPE;
BEGIN
  SELECT * INTO d FROM merchant.declaration WHERE declaration_id = p_declaration FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'declaration % not found', p_declaration; END IF;
  IF d.status NOT IN ('draft','needs_info') THEN RAISE EXCEPTION 'declaration is %', d.status USING ERRCODE = 'check_violation'; END IF;
  IF p_menu_as_of > ref.today_tpe() OR p_menu_as_of < ref.today_tpe() - 180 THEN
    RAISE EXCEPTION 'menu_as_of must be within the last 180 days' USING ERRCODE = 'check_violation';
  END IF;
  UPDATE merchant.declaration SET status = 'submitted', declared_role = p_role, menu_as_of = p_menu_as_of, attestation_version = p_attestation_version,
         attested_at = now(), submitted_at = now() WHERE declaration_id = p_declaration;
END $$;

-- What publishing WOULD write, and what it would contradict. Used by both the reviewer's preview and publish_declaration (one source of truth).
--   state:  strong claim -> CONFIRMED_*, basic claim -> LIKELY_*; halal "offered" needs a certificate reference to be confirmed
--   cross contact (critical allergens only, "absent_entire_menu"): confirmed_none keeps the state; possible/unknown cap it at LIKELY_ABSENT
--           (the engine then raises a critical warning, never a safe badge); confirmed_shared turns it into LIKELY_PRESENT (the engine excludes the restaurant)
CREATE FUNCTION merchant.declaration_plan(p_declaration BIGINT)
RETURNS TABLE (attribute_code TEXT, attribute_type TEXT, answer TEXT, cross_contact_status TEXT, new_state ref.evidence_state, evidence_basis TEXT, confidence TEXT,
               presence_extent TEXT, capped_by_cross_contact BOOLEAN, conflicts BIGINT[], conflicts_confirmed BOOLEAN)
LANGUAGE sql STABLE AS $$
  WITH d AS (
    SELECT dc.restaurant_id, dc.menu_url, dc.menu_file_ref, c.verification_level AS vlevel
      FROM merchant.declaration dc JOIN merchant.claim c USING (claim_id) WHERE dc.declaration_id = p_declaration),
  raw AS (
    SELECT i.attribute_code AS attr, a.attribute_type AS atype, a.risk_level, i.answer AS ans, i.cross_contact_status AS cc, i.certificate_ref,
           d.restaurant_id, d.menu_url, d.menu_file_ref, d.vlevel,
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
         AND e.source_id <> (SELECT source_id FROM ref.data_source WHERE source_type = 'first_party')
         AND (e.valid_until IS NULL OR e.valid_until >= ref.today_tpe())
         AND ((c.st IN ('CONFIRMED_ABSENT','LIKELY_ABSENT') AND e.state IN ('CONFIRMED_PRESENT','LIKELY_PRESENT'))
           OR (c.st IN ('CONFIRMED_PRESENT','LIKELY_PRESENT') AND e.state IN ('CONFIRMED_ABSENT','LIKELY_ABSENT')))
    ) x ON TRUE
$$;

-- Publish = approve + write first-party evidence. Contradictions are never resolved silently:
--   LIKELY_* contradictions block publishing unless the reviewer passes p_supersede (recorded in the audit log); CONFIRMED_* contradictions always block.
CREATE FUNCTION merchant.publish_declaration(p_declaration BIGINT, p_reviewer TEXT, p_supersede BOOLEAN DEFAULT FALSE) RETURNS INT LANGUAGE plpgsql AS $$
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
  SELECT source_id INTO v_src FROM ref.data_source WHERE source_type = 'first_party';
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

CREATE FUNCTION merchant.review_declaration(p_declaration BIGINT, p_outcome TEXT, p_reviewer TEXT, p_note TEXT) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE d merchant.declaration%ROWTYPE;
BEGIN
  IF p_outcome NOT IN ('rejected','needs_info') THEN RAISE EXCEPTION 'outcome must be rejected or needs_info' USING ERRCODE = 'check_violation'; END IF;
  IF p_reviewer IS NULL OR btrim(p_reviewer) = '' THEN RAISE EXCEPTION 'a named reviewer is required' USING ERRCODE = 'check_violation'; END IF;
  SELECT * INTO d FROM merchant.declaration WHERE declaration_id = p_declaration FOR UPDATE;
  IF NOT FOUND OR d.status <> 'submitted' THEN RAISE EXCEPTION 'only a submitted declaration can be reviewed (status: %)', COALESCE(d.status, 'missing') USING ERRCODE = 'check_violation'; END IF;
  PERFORM set_config('joeat.actor', p_reviewer, true);
  UPDATE merchant.declaration SET status = p_outcome, reviewed_by = p_reviewer, reviewed_at = now(), review_note = p_note WHERE declaration_id = p_declaration;
END $$;

-- ============================================================ 7. kill switch (suspends POSITIVE claims only)
CREATE FUNCTION merchant.incident_kill_switch() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.severity IN ('allergic_reaction','wrong_info') THEN
    UPDATE enrichment.restaurant_attribute_evidence e SET status = 'suspended', suspended_by_incident = NEW.incident_id
      FROM ref.attribute a
     WHERE a.attribute_code = e.attribute_code AND e.restaurant_id = NEW.restaurant_id AND e.declaration_id IS NOT NULL AND e.status = 'active'
       AND ((a.attribute_type = 'avoid' AND e.state IN ('CONFIRMED_ABSENT','LIKELY_ABSENT')) OR (a.attribute_type = 'require' AND e.state IN ('CONFIRMED_PRESENT','LIKELY_PRESENT')))
       AND (NEW.severity = 'allergic_reaction' OR NEW.attribute_code IS NULL OR NEW.attribute_code = e.attribute_code);
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER incident_kill_switch_trg AFTER INSERT ON merchant.incident_report FOR EACH ROW EXECUTE FUNCTION merchant.incident_kill_switch();

CREATE FUNCTION merchant.resolve_incident(p_incident BIGINT, p_outcome TEXT, p_reviewer TEXT) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE r merchant.incident_report%ROWTYPE;
BEGIN
  IF p_outcome NOT IN ('confirmed','dismissed') THEN RAISE EXCEPTION 'outcome must be confirmed or dismissed' USING ERRCODE = 'check_violation'; END IF;
  SELECT * INTO r FROM merchant.incident_report WHERE incident_id = p_incident FOR UPDATE;
  IF NOT FOUND OR r.status <> 'open' THEN RAISE EXCEPTION 'incident is not open' USING ERRCODE = 'check_violation'; END IF;
  IF p_outcome = 'dismissed' THEN
    UPDATE enrichment.restaurant_attribute_evidence SET status = 'active', suspended_by_incident = NULL WHERE suspended_by_incident = p_incident;
  ELSE
    UPDATE enrichment.restaurant_attribute_evidence SET status = 'superseded' WHERE suspended_by_incident = p_incident;
    UPDATE merchant.claim SET status = 'revoked' WHERE restaurant_id = r.restaurant_id AND status = 'verified';
  END IF;
  UPDATE merchant.incident_report SET status = p_outcome, handled_by = p_reviewer, handled_at = now() WHERE incident_id = p_incident;
END $$;
