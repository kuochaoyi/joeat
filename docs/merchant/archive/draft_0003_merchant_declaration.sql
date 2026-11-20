-- draft_0003_merchant_declaration.sql  -- DESIGN DRAFT, not wired into Alembic yet.
-- Applies on top of schema_v2 + migration 0002. Validated on PostgreSQL 16.2 by validate_draft.py (see validation_results.txt).
--
-- What it adds
--   merchant.claim / declaration / declaration_item / declaration_audit / incident_report
--   evidence lifecycle on enrichment.restaurant_attribute_evidence (status, superseded_by, declaration_id, suspended_by_incident)
--   merchant.publish_declaration(): turns an APPROVED declaration into first-party evidence, under the existing evidence rules
--   a kill switch: an incident report suspends the restaurant's positive (safety) claims until a human resolves it
-- What it does NOT change: the hard-filter rules, the decision matrix, the scoring, the API of the recommendation engine.

BEGIN;
CREATE SCHEMA IF NOT EXISTS merchant;

-- ============================================================ 1. who may speak for a restaurant
CREATE TABLE merchant.claim (
  claim_id            BIGSERIAL PRIMARY KEY,
  restaurant_id       UUID NOT NULL REFERENCES identity.restaurant,
  token_hash          TEXT NOT NULL UNIQUE,            -- SHA-256 of the invite token; the raw token is shown once and never stored
  status              TEXT NOT NULL DEFAULT 'invited' CHECK (status IN ('invited','verified','revoked','expired')),
  verification_method TEXT CHECK (verification_method IN ('phone_callback','onsite_visit','operator_known','official_channel_message')),
  verification_level  TEXT NOT NULL DEFAULT 'none' CHECK (verification_level IN ('none','basic','strong')),
  verified_by         TEXT, verified_at TIMESTAMPTZ,
  claimant_line_ref   TEXT,                             -- hashed LINE user id of the person who opened the link
  claimant_role       TEXT CHECK (claimant_role IN ('owner','manager','staff')),
  invited_by          TEXT NOT NULL,
  invited_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at          TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '30 days'),
  CONSTRAINT claim_pair UNIQUE (claim_id, restaurant_id),
  CONSTRAINT claim_verified_needs_proof CHECK (status <> 'verified' OR (verification_method IS NOT NULL AND verified_by IS NOT NULL AND verified_at IS NOT NULL AND verification_level <> 'none')),
  -- only a channel we can call back / see in person is "strong" (strong may produce CONFIRMED_* evidence; basic may only produce LIKELY_*)
  CONSTRAINT claim_strong_methods CHECK (verification_level <> 'strong' OR verification_method IN ('phone_callback','onsite_visit','operator_known'))
);
CREATE INDEX claim_restaurant ON merchant.claim (restaurant_id);

-- ============================================================ 2. what they declare
CREATE TABLE merchant.declaration (
  declaration_id   BIGSERIAL PRIMARY KEY,
  claim_id         BIGINT NOT NULL,
  restaurant_id    UUID NOT NULL,
  status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','submitted','needs_info','approved','rejected','withdrawn')),
  valid_days       SMALLINT NOT NULL DEFAULT 90 CHECK (valid_days BETWEEN 1 AND 180),   -- 180 = hard ceiling already enforced on evidence
  menu_as_of       DATE,                                -- the menu version this declaration describes
  menu_url         TEXT, menu_file_ref TEXT,            -- optional proof; makes the basis 'official_menu' instead of 'restaurant_declaration'
  declared_role    TEXT CHECK (declared_role IN ('owner','manager','staff')),
  attestation_version TEXT, attested_at TIMESTAMPTZ,
  submitted_at     TIMESTAMPTZ, reviewed_by TEXT, reviewed_at TIMESTAMPTZ, review_note TEXT,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT decl_claim_fk FOREIGN KEY (claim_id, restaurant_id) REFERENCES merchant.claim (claim_id, restaurant_id),   -- a claim can only speak for its own restaurant
  CONSTRAINT decl_submitted_needs_attestation CHECK (status NOT IN ('submitted','approved') OR (attested_at IS NOT NULL AND menu_as_of IS NOT NULL AND declared_role IS NOT NULL)),
  CONSTRAINT decl_approved_needs_reviewer CHECK (status <> 'approved' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))
);
CREATE INDEX declaration_restaurant ON merchant.declaration (restaurant_id, status);

CREATE TABLE merchant.declaration_item (
  declaration_id BIGINT NOT NULL REFERENCES merchant.declaration ON DELETE CASCADE,
  attribute_code TEXT NOT NULL REFERENCES ref.attribute,
  answer         TEXT NOT NULL DEFAULT 'not_sure'      -- the default is NEVER "absent": silence must stay UNKNOWN
                 CHECK (answer IN ('absent_entire_menu','present_in_some_dishes','present_in_most_dishes','offered','not_offered','not_sure')),
  cross_contact  TEXT NOT NULL DEFAULT 'not_sure' CHECK (cross_contact IN ('none_known','possible','not_sure')),
  note           TEXT,
  certificate_ref TEXT,                                -- e.g. halal certificate number
  PRIMARY KEY (declaration_id, attribute_code)
);

CREATE TABLE merchant.declaration_audit (               -- append-only
  audit_id BIGSERIAL PRIMARY KEY, declaration_id BIGINT NOT NULL REFERENCES merchant.declaration,
  event TEXT NOT NULL, actor TEXT, at TIMESTAMPTZ NOT NULL DEFAULT now(), detail JSONB
);

CREATE TABLE merchant.incident_report (
  incident_id   BIGSERIAL PRIMARY KEY,
  restaurant_id UUID NOT NULL REFERENCES identity.restaurant,
  attribute_code TEXT REFERENCES ref.attribute,
  severity      TEXT NOT NULL CHECK (severity IN ('allergic_reaction','wrong_info','other')),
  reporter_ref  TEXT,                                   -- hashed; may be NULL for anonymous reports
  description   TEXT,
  status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','confirmed','dismissed')),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(), handled_by TEXT, handled_at TIMESTAMPTZ,
  CHECK ((status = 'open') = (handled_at IS NULL))
);
CREATE INDEX incident_restaurant ON merchant.incident_report (restaurant_id, status);

-- ============================================================ 3. guards (enforced by the database, not by convention)
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
    IF OLD.status <> 'draft' THEN RAISE EXCEPTION 'only draft declarations can be deleted (history is kept)' USING ERRCODE = 'check_violation'; END IF;
    RETURN OLD;
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

-- the trail starts at creation, not at the first status change
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

-- ============================================================ 4. evidence lifecycle (so a declaration can replace, and an incident can suspend)
ALTER TABLE enrichment.restaurant_attribute_evidence
  ADD COLUMN status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','superseded','suspended')),
  ADD COLUMN superseded_by BIGINT REFERENCES enrichment.restaurant_attribute_evidence (evidence_id),
  ADD COLUMN declaration_id BIGINT REFERENCES merchant.declaration (declaration_id),
  ADD COLUMN suspended_by_incident BIGINT REFERENCES merchant.incident_report (incident_id);
CREATE INDEX evidence_declaration ON enrichment.restaurant_attribute_evidence (declaration_id) WHERE declaration_id IS NOT NULL;

-- only ACTIVE evidence counts (columns are appended, so CREATE OR REPLACE VIEW is allowed)
CREATE OR REPLACE VIEW enrichment.v_evidence_valid AS
SELECT e.* FROM enrichment.restaurant_attribute_evidence e
JOIN ref.data_source s USING (source_id)
WHERE e.status = 'active'
  AND (e.valid_until IS NULL OR e.valid_until >= ref.today_tpe())
  AND (NOT s.is_test OR coalesce(current_setting('joeat.allow_test_evidence', true), 'off') = 'on');

-- an UNVERIFIED-channel declaration of absence may only be LIKELY_ABSENT (never CONFIRMED_ABSENT): allow that pair
INSERT INTO ref.evidence_state_basis_rule (state, basis) VALUES ('LIKELY_ABSENT', 'restaurant_declaration') ON CONFLICT DO NOTHING;

-- ============================================================ 5. workflow functions
CREATE FUNCTION merchant.start_declaration(p_claim BIGINT, p_valid_days INT DEFAULT 90) RETURNS BIGINT LANGUAGE plpgsql AS $$
DECLARE c merchant.claim%ROWTYPE; v_id BIGINT;
BEGIN
  SELECT * INTO c FROM merchant.claim WHERE claim_id = p_claim FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'claim % not found', p_claim; END IF;
  IF c.status <> 'verified' THEN RAISE EXCEPTION 'claim is % : only a verified claim can declare', c.status USING ERRCODE = 'check_violation'; END IF;
  IF c.expires_at < now() THEN RAISE EXCEPTION 'claim expired' USING ERRCODE = 'check_violation'; END IF;
  INSERT INTO merchant.declaration (claim_id, restaurant_id, valid_days) VALUES (c.claim_id, c.restaurant_id, p_valid_days) RETURNING declaration_id INTO v_id;
  INSERT INTO merchant.declaration_item (declaration_id, attribute_code) SELECT v_id, attribute_code FROM ref.attribute WHERE is_active;   -- every attribute starts as not_sure
  RETURN v_id;
END $$;

CREATE FUNCTION merchant.submit_declaration(p_declaration BIGINT, p_role TEXT, p_menu_as_of DATE, p_attestation_version TEXT) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE d merchant.declaration%ROWTYPE;
BEGIN
  SELECT * INTO d FROM merchant.declaration WHERE declaration_id = p_declaration FOR UPDATE;
  IF d.status NOT IN ('draft','needs_info') THEN RAISE EXCEPTION 'declaration is %', d.status USING ERRCODE = 'check_violation'; END IF;
  IF p_menu_as_of > ref.today_tpe() OR p_menu_as_of < ref.today_tpe() - 180 THEN
    RAISE EXCEPTION 'menu_as_of must be within the last 180 days' USING ERRCODE = 'check_violation';
  END IF;
  UPDATE merchant.declaration SET status = 'submitted', declared_role = p_role, menu_as_of = p_menu_as_of, attestation_version = p_attestation_version,
         attested_at = now(), submitted_at = now() WHERE declaration_id = p_declaration;
END $$;

-- Publish = approve + write first-party evidence. Contradictions with existing evidence are never resolved silently:
--   * LIKELY_* contradictions block publishing unless the reviewer passes p_supersede = true (recorded in the audit log)
--   * CONFIRMED_* contradictions always block: fix or reject the declaration first
CREATE FUNCTION merchant.publish_declaration(p_declaration BIGINT, p_reviewer TEXT, p_supersede BOOLEAN DEFAULT FALSE) RETURNS INT LANGUAGE plpgsql AS $$
DECLARE
  d merchant.declaration%ROWTYPE; c merchant.claim%ROWTYPE; it RECORD; v_src SMALLINT; v_today DATE := ref.today_tpe();
  v_state ref.evidence_state; v_basis TEXT; v_conf TEXT; v_text TEXT; v_new BIGINT; v_n INT := 0; v_ids BIGINT[]; v_bad BIGINT[];
BEGIN
  IF p_reviewer IS NULL OR p_reviewer = '' THEN RAISE EXCEPTION 'a named reviewer is required' USING ERRCODE = 'check_violation'; END IF;
  SELECT * INTO d FROM merchant.declaration WHERE declaration_id = p_declaration FOR UPDATE;
  IF NOT FOUND OR d.status <> 'submitted' THEN RAISE EXCEPTION 'only a submitted declaration can be published (status: %)', COALESCE(d.status, 'missing') USING ERRCODE = 'check_violation'; END IF;
  SELECT * INTO c FROM merchant.claim WHERE claim_id = d.claim_id;
  IF c.status <> 'verified' THEN RAISE EXCEPTION 'claim is % : cannot publish', c.status USING ERRCODE = 'check_violation'; END IF;
  SELECT source_id INTO v_src FROM ref.data_source WHERE source_type = 'first_party';

  FOR it IN SELECT i.*, a.attribute_type, a.display_name_zh FROM merchant.declaration_item i JOIN ref.attribute a USING (attribute_code) WHERE i.declaration_id = p_declaration LOOP
    CONTINUE WHEN it.answer = 'not_sure';
    -- 1) answer -> evidence state, gated by how strongly the claimant was verified
    IF it.attribute_type = 'avoid' THEN
      IF it.answer = 'absent_entire_menu' THEN v_state := CASE WHEN c.verification_level = 'strong' THEN 'CONFIRMED_ABSENT' ELSE 'LIKELY_ABSENT' END;
      ELSE v_state := CASE WHEN c.verification_level = 'strong' THEN 'CONFIRMED_PRESENT' ELSE 'LIKELY_PRESENT' END; END IF;
    ELSE
      IF it.answer = 'offered' THEN v_state := CASE WHEN c.verification_level = 'strong' AND (it.attribute_code <> 'halal' OR it.certificate_ref IS NOT NULL) THEN 'CONFIRMED_PRESENT' ELSE 'LIKELY_PRESENT' END;
      ELSE v_state := CASE WHEN c.verification_level = 'strong' THEN 'CONFIRMED_ABSENT' ELSE 'LIKELY_ABSENT' END; END IF;
    END IF;
    v_basis := CASE WHEN (d.menu_url IS NOT NULL OR d.menu_file_ref IS NOT NULL) AND v_state IN ('CONFIRMED_ABSENT','CONFIRMED_PRESENT','LIKELY_PRESENT') THEN 'official_menu' ELSE 'restaurant_declaration' END;
    v_conf := CASE WHEN v_state IN ('CONFIRMED_ABSENT','CONFIRMED_PRESENT') THEN 'HIGH' ELSE 'MEDIUM' END;
    v_text := format('店家聲明（%s，%s，菜單日期 %s）：%s%s', v_today, c.claimant_role, d.menu_as_of, it.answer,
                     CASE it.cross_contact WHEN 'possible' THEN '；共用設備：可能' WHEN 'none_known' THEN '；共用設備：無已知' ELSE '' END || COALESCE('；' || it.note, ''));

    -- 2) contradictions with other active evidence of the opposite polarity
    SELECT array_agg(e.evidence_id) INTO v_bad FROM enrichment.restaurant_attribute_evidence e JOIN ref.attribute a USING (attribute_code)
     WHERE e.restaurant_id = d.restaurant_id AND e.attribute_code = it.attribute_code AND e.status = 'active' AND e.source_id <> v_src
       AND (e.valid_until IS NULL OR e.valid_until >= v_today)
       AND ((a.attribute_type = 'avoid'   AND ((v_state IN ('CONFIRMED_ABSENT','LIKELY_ABSENT') AND e.state IN ('CONFIRMED_PRESENT','LIKELY_PRESENT'))
                                            OR (v_state IN ('CONFIRMED_PRESENT','LIKELY_PRESENT') AND e.state IN ('CONFIRMED_ABSENT','LIKELY_ABSENT'))))
         OR (a.attribute_type = 'require' AND ((v_state IN ('CONFIRMED_PRESENT','LIKELY_PRESENT') AND e.state IN ('CONFIRMED_ABSENT','LIKELY_ABSENT'))
                                            OR (v_state IN ('CONFIRMED_ABSENT','LIKELY_ABSENT') AND e.state IN ('CONFIRMED_PRESENT','LIKELY_PRESENT')))));
    IF v_bad IS NOT NULL THEN
      IF EXISTS (SELECT 1 FROM enrichment.restaurant_attribute_evidence WHERE evidence_id = ANY (v_bad) AND state IN ('CONFIRMED_PRESENT','CONFIRMED_ABSENT')) THEN
        RAISE EXCEPTION 'contradiction with CONFIRMED evidence % on attribute %: resolve the data or reject the declaration', v_bad, it.attribute_code USING ERRCODE = 'check_violation';
      ELSIF NOT p_supersede THEN
        RAISE EXCEPTION 'contradiction with existing evidence % on attribute %: review it, then publish with p_supersede = true', v_bad, it.attribute_code USING ERRCODE = 'check_violation';
      END IF;
    END IF;

    -- 3) upsert the first-party evidence (a renewal updates the same row, history lives in declaration_item / audit)
    INSERT INTO enrichment.restaurant_attribute_evidence
      (restaurant_id, attribute_code, state, evidence_text, evidence_basis, applies_to, source_id, source_url, confidence, observed_at, last_verified_at, valid_until, declaration_id, status)
    VALUES (d.restaurant_id, it.attribute_code, v_state, v_text, v_basis, 'this_branch', v_src, d.menu_url, v_conf, LEAST(d.menu_as_of, v_today), v_today, v_today + d.valid_days, p_declaration, 'active')
    ON CONFLICT ON CONSTRAINT evidence_unique DO UPDATE SET state = EXCLUDED.state, evidence_text = EXCLUDED.evidence_text, source_url = EXCLUDED.source_url, confidence = EXCLUDED.confidence,
      observed_at = EXCLUDED.observed_at, last_verified_at = EXCLUDED.last_verified_at, valid_until = EXCLUDED.valid_until, declaration_id = EXCLUDED.declaration_id, status = 'active',
      superseded_by = NULL, suspended_by_incident = NULL
    RETURNING evidence_id INTO v_new;
    v_n := v_n + 1;

    IF v_bad IS NOT NULL THEN
      UPDATE enrichment.restaurant_attribute_evidence SET status = 'superseded', superseded_by = v_new WHERE evidence_id = ANY (v_bad);
      INSERT INTO merchant.declaration_audit (declaration_id, event, actor, detail)
      VALUES (p_declaration, 'superseded_third_party_evidence', p_reviewer, jsonb_build_object('attribute', it.attribute_code, 'superseded', v_bad, 'by', v_new));
    END IF;
  END LOOP;

  -- 4) earlier first-party evidence for this restaurant that this declaration did not re-assert is retired (a new declaration replaces the old one)
  UPDATE enrichment.restaurant_attribute_evidence SET status = 'superseded'
   WHERE restaurant_id = d.restaurant_id AND source_id = v_src AND status = 'active' AND declaration_id IS DISTINCT FROM p_declaration;

  PERFORM set_config('joeat.actor', p_reviewer, true);
  UPDATE merchant.declaration SET status = 'approved', reviewed_by = p_reviewer, reviewed_at = now() WHERE declaration_id = p_declaration;
  RETURN v_n;
END $$;

-- ============================================================ 6. kill switch
-- Suspend only POSITIVE (safety) claims: absence of an avoided thing, or presence of a required thing. Suspending a "contains X" claim would make a venue look safer.
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
  IF p_outcome NOT IN ('confirmed','dismissed') THEN RAISE EXCEPTION 'outcome must be confirmed or dismissed'; END IF;
  SELECT * INTO r FROM merchant.incident_report WHERE incident_id = p_incident FOR UPDATE;
  IF NOT FOUND OR r.status <> 'open' THEN RAISE EXCEPTION 'incident is not open'; END IF;
  IF p_outcome = 'dismissed' THEN
    UPDATE enrichment.restaurant_attribute_evidence SET status = 'active', suspended_by_incident = NULL WHERE suspended_by_incident = p_incident;   -- expired ones stay invisible through valid_until
  ELSE
    UPDATE enrichment.restaurant_attribute_evidence SET status = 'superseded' WHERE suspended_by_incident = p_incident;
    UPDATE merchant.claim SET status = 'revoked' WHERE restaurant_id = r.restaurant_id AND status = 'verified';
  END IF;
  UPDATE merchant.incident_report SET status = p_outcome, handled_by = p_reviewer, handled_at = now() WHERE incident_id = p_incident;
END $$;

COMMIT;
