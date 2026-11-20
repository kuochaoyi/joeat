-- schema_v2.sql  (PostgreSQL 14+; validated on PostgreSQL 16.2, see schema_validation_report.md)
-- v2.1 patch: evaluate_session() scored an UNKNOWN distance as -1 (found by the Python-vs-SQL parity test in the MVP); it is now 0 as the contract says.
-- Layers: ref -> staging -> identity -> enrichment -> product
-- Principles
--   1. Discovery / identity / enrichment / recommendation are separate concerns.
--   2. Every enrichment fact is EVIDENCE: source + confidence + last_verified_at (+ valid_until). No evidence row = UNKNOWN, never "safe".
--   3. Policy that matters (no personal names, safety claims need first-party evidence, claims expire) is enforced by the database, not by convention.
--   4. Time: all instants are TIMESTAMPTZ; "verified on" fields are DATE in Taiwan time (UTC+8) via ref.today_tpe(); views never use CURRENT_DATE.
--   5. Budget, price, rating and Google hours are NOT assumed to exist; they only appear as nullable / UNKNOWN components.

CREATE SCHEMA IF NOT EXISTS ref;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS enrichment;
CREATE SCHEMA IF NOT EXISTS product;

-- ===================================================================== helpers
CREATE FUNCTION ref.today_tpe() RETURNS date LANGUAGE sql STABLE AS
$$ SELECT ((now() AT TIME ZONE 'UTC') + interval '8 hours')::date $$;   -- Taiwan is fixed UTC+8 (no DST since 1979); avoids a tzdata dependency

CREATE FUNCTION ref.set_updated_at() RETURNS trigger LANGUAGE plpgsql AS
$$ BEGIN NEW.updated_at := now(); RETURN NEW; END $$;

CREATE FUNCTION ref.haversine_m(lat1 double precision, lon1 double precision, lat2 double precision, lon2 double precision)
RETURNS double precision LANGUAGE sql IMMUTABLE AS
$$ SELECT 2 * 6371000.0 * asin(sqrt(
     power(sin(radians(lat2 - lat1) / 2), 2) +
     cos(radians(lat1)) * cos(radians(lat2)) * power(sin(radians(lon2 - lon1) / 2), 2))) $$;

CREATE FUNCTION ref.risk_rank(r text) RETURNS smallint LANGUAGE sql IMMUTABLE AS
$$ SELECT CASE r WHEN 'critical' THEN 3 WHEN 'high' THEN 2 WHEN 'normal' THEN 1 END::smallint $$;

-- ===================================================================== ref: dictionaries
CREATE TABLE ref.data_source (
  source_id          SMALLINT PRIMARY KEY,
  source_type        TEXT NOT NULL UNIQUE,   -- tax | osm | places | gov_tourism | blog_media | aggregator | first_party | derived | test_fixture
  is_first_party     BOOLEAN NOT NULL DEFAULT FALSE,   -- only first-party sources may justify CONFIRMED_ABSENT
  is_test            BOOLEAN NOT NULL DEFAULT FALSE,   -- test fixtures are invisible unless joeat.allow_test_evidence = 'on'
  default_confidence TEXT NOT NULL CHECK (default_confidence IN ('HIGH','MEDIUM','LOW','UNKNOWN')),
  license_note       TEXT,
  retention_note     TEXT,
  CHECK (NOT (is_test AND is_first_party AND source_type <> 'test_fixture'))
);

CREATE TABLE ref.cuisine_tag (tag TEXT PRIMARY KEY, parent_tag TEXT REFERENCES ref.cuisine_tag);

CREATE TABLE ref.tax_industry_map (
  industry_code TEXT PRIMARY KEY, industry_name TEXT NOT NULL,
  pool_class TEXT NOT NULL CHECK (pool_class IN ('candidate','excluded_drink','excluded_bar','excluded_stall','excluded_other'))
);

CREATE TYPE ref.evidence_state AS ENUM ('CONFIRMED_PRESENT','LIKELY_PRESENT','LIKELY_ABSENT','CONFIRMED_ABSENT','UNKNOWN');

CREATE TABLE ref.evidence_state_def (
  state ref.evidence_state PRIMARY KEY,
  meaning_zh TEXT NOT NULL, allowed_basis_note TEXT NOT NULL,
  usable_for_hard_constraint BOOLEAN NOT NULL,      -- may this state, alone, trigger an exclusion / pass?
  may_show_safe BOOLEAN NOT NULL                    -- may the UI render a positive "safe/ok" signal for it?
);

CREATE TABLE ref.evidence_basis (
  basis TEXT PRIMARY KEY, is_first_party_basis BOOLEAN NOT NULL, description TEXT NOT NULL
);

CREATE TABLE ref.evidence_state_basis_rule (       -- which (state, basis) pairs are legal
  state ref.evidence_state NOT NULL, basis TEXT NOT NULL REFERENCES ref.evidence_basis,
  PRIMARY KEY (state, basis)
);

CREATE TABLE ref.attribute (
  attribute_code TEXT PRIMARY KEY,
  display_name_zh TEXT NOT NULL,
  attribute_type TEXT NOT NULL CHECK (attribute_type IN ('avoid','require')),
  risk_level TEXT NOT NULL CHECK (risk_level IN ('critical','high','normal')),
  description TEXT NOT NULL,
  default_unknown_behavior TEXT NOT NULL CHECK (default_unknown_behavior IN ('warn_critical','warn','note')),
  sort_order SMALLINT NOT NULL DEFAULT 0,
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE ref.attribute_implication (            -- sub present => super present ; super absent => sub absent
  sub_attr TEXT NOT NULL REFERENCES ref.attribute, super_attr TEXT NOT NULL REFERENCES ref.attribute,
  PRIMARY KEY (sub_attr, super_attr), CHECK (sub_attr <> super_attr)
);

CREATE TABLE ref.constraint_reason (                 -- why a participant has the constraint; raises (never lowers) the effective risk
  reason TEXT PRIMARY KEY, min_risk_level TEXT NOT NULL CHECK (min_risk_level IN ('critical','high','normal')), label_zh TEXT NOT NULL
);

CREATE TABLE ref.constraint_decision_rule (          -- the executable half of recommendation_data_contract.md
  attribute_type TEXT NOT NULL CHECK (attribute_type IN ('avoid','require')),
  risk_level     TEXT NOT NULL CHECK (risk_level IN ('critical','high','normal')),
  state          ref.evidence_state NOT NULL,
  action         TEXT NOT NULL CHECK (action IN ('PASS','PASS_CONDITIONAL','WARN','EXCLUDE')),
  warning_level  TEXT NOT NULL CHECK (warning_level IN ('none','normal','high','critical')),
  may_show_safe_badge BOOLEAN NOT NULL DEFAULT FALSE,
  note TEXT,
  PRIMARY KEY (attribute_type, risk_level, state),
  CHECK (NOT may_show_safe_badge OR action = 'PASS'),
  CHECK (action <> 'EXCLUDE' OR warning_level = 'none')
);

CREATE TABLE ref.scoring_config (
  version TEXT PRIMARY KEY, config JSONB NOT NULL, is_active BOOLEAN NOT NULL DEFAULT FALSE,
  note TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX scoring_config_one_active ON ref.scoring_config (is_active) WHERE is_active;

-- ===================================================================== staging
CREATE TABLE staging.tax_registry (
  tax_record_id    TEXT PRIMARY KEY,                -- 統一編號 || '|' || 營業地址
  business_address TEXT NOT NULL,
  address_key      TEXT,
  industry_code    TEXT NOT NULL, secondary_codes TEXT[],
  established_on   DATE, org_type TEXT, uses_invoice BOOLEAN,
  business_name    TEXT,
  name_is_personal BOOLEAN NOT NULL DEFAULT FALSE,
  snapshot_date    DATE NOT NULL,
  CONSTRAINT tax_no_personal_name CHECK (NOT name_is_personal OR business_name IS NULL)
);
CREATE INDEX tax_registry_address_key ON staging.tax_registry (address_key);

CREATE TABLE staging.osm_poi (
  osm_id TEXT PRIMARY KEY, lat DOUBLE PRECISION NOT NULL CHECK (lat BETWEEN -90 AND 90), lon DOUBLE PRECISION NOT NULL CHECK (lon BETWEEN -180 AND 180),
  tags JSONB NOT NULL, snapshot_at TIMESTAMPTZ NOT NULL
);
-- places_raw intentionally absent: store only place_id (+ short-lived cache) until the Places terms review is done.

-- ===================================================================== identity
CREATE TABLE identity.restaurant (
  restaurant_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_name    TEXT NOT NULL,
  canonical_address TEXT, address_key TEXT,
  district          TEXT NOT NULL, city TEXT NOT NULL,
  lat DOUBLE PRECISION, lon DOUBLE PRECISION,       -- NULL = unknown (geocode later)
  phone             TEXT,
  active_status     TEXT NOT NULL DEFAULT 'unverified' CHECK (active_status IN ('active','unverified','closed','not_a_restaurant')),
  pool_status       TEXT NOT NULL DEFAULT 'candidate' CHECK (pool_status IN ('candidate','in_pool','excluded')),
  pool_reason       TEXT,
  status_verified_at DATE,
  merged_into_restaurant_id UUID REFERENCES identity.restaurant,   -- ER merges re-point; rows are never hard-deleted once referenced by a run
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT restaurant_latlon_pair  CHECK ((lat IS NULL) = (lon IS NULL)),
  CONSTRAINT restaurant_lat_range    CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),
  CONSTRAINT restaurant_lon_range    CHECK (lon IS NULL OR lon BETWEEN -180 AND 180),
  CONSTRAINT restaurant_pool_vs_active CHECK (pool_status <> 'in_pool' OR active_status IN ('active','unverified')),
  CONSTRAINT restaurant_no_self_merge CHECK (merged_into_restaurant_id IS NULL OR merged_into_restaurant_id <> restaurant_id)
);
CREATE TRIGGER restaurant_touch BEFORE UPDATE ON identity.restaurant FOR EACH ROW EXECUTE FUNCTION ref.set_updated_at();
CREATE INDEX restaurant_pool ON identity.restaurant (district, pool_status) WHERE merged_into_restaurant_id IS NULL;
CREATE INDEX restaurant_address_key ON identity.restaurant (address_key);
CREATE INDEX restaurant_merged_into ON identity.restaurant (merged_into_restaurant_id) WHERE merged_into_restaurant_id IS NOT NULL;

CREATE TABLE identity.restaurant_source_entity (
  source_entity_id  BIGSERIAL PRIMARY KEY,
  restaurant_id     UUID REFERENCES identity.restaurant,                -- NULL = unresolved candidate
  source_id         SMALLINT NOT NULL REFERENCES ref.data_source,
  source_record_id  TEXT NOT NULL,
  source_name       TEXT,
  source_name_is_personal BOOLEAN NOT NULL DEFAULT FALSE,
  source_address    TEXT, address_key TEXT, industry_code TEXT, source_url TEXT,
  matched_by        TEXT CHECK (matched_by IN ('same_address+name','name_only','coord+name','alias','manual')),
  match_score       REAL, match_features JSONB, er_version TEXT,
  match_status      TEXT NOT NULL DEFAULT 'review' CHECK (match_status IN ('auto','probable','review','rejected','manual_confirmed')),
  first_seen_at DATE, last_seen_at DATE,
  CONSTRAINT source_entity_unique UNIQUE (source_id, source_record_id),
  CONSTRAINT source_entity_no_personal_name CHECK (NOT source_name_is_personal OR source_name IS NULL),
  CONSTRAINT source_entity_status_vs_link CHECK (
    (restaurant_id IS NOT NULL AND match_status IN ('auto','probable','manual_confirmed')) OR
    (restaurant_id IS NULL     AND match_status IN ('review','rejected')))
);
CREATE INDEX source_entity_restaurant ON identity.restaurant_source_entity (restaurant_id);
CREATE INDEX source_entity_address_key ON identity.restaurant_source_entity (address_key);

CREATE TABLE identity.restaurant_alias (
  restaurant_id UUID NOT NULL REFERENCES identity.restaurant ON DELETE CASCADE,
  alias TEXT NOT NULL, origin TEXT NOT NULL, PRIMARY KEY (restaurant_id, alias)
);

CREATE TABLE identity.er_review_queue (
  review_id BIGSERIAL PRIMARY KEY,
  source_entity_id BIGINT NOT NULL REFERENCES identity.restaurant_source_entity ON DELETE CASCADE,
  candidate_restaurant_id UUID REFERENCES identity.restaurant,
  reason TEXT NOT NULL, features JSONB,
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','decided')),
  decision TEXT CHECK (decision IN ('match','not_match','new_restaurant','not_a_restaurant')),
  decided_by TEXT, decided_at TIMESTAMPTZ,
  CHECK ((status = 'decided') = (decision IS NOT NULL))
);
CREATE INDEX er_review_open ON identity.er_review_queue (status) WHERE status = 'open';
CREATE INDEX er_review_source ON identity.er_review_queue (source_entity_id);
CREATE INDEX er_review_candidate ON identity.er_review_queue (candidate_restaurant_id) WHERE candidate_restaurant_id IS NOT NULL;

CREATE TABLE identity.er_config (                     -- provisional thresholds live in data, versioned, never hard-coded
  version TEXT PRIMARY KEY, config JSONB NOT NULL,
  status TEXT NOT NULL DEFAULT 'provisional' CHECK (status IN ('provisional','validated','retired')),
  note TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ===================================================================== enrichment
CREATE TABLE enrichment.restaurant_cuisine (
  restaurant_id UUID NOT NULL REFERENCES identity.restaurant ON DELETE CASCADE,
  tag TEXT NOT NULL REFERENCES ref.cuisine_tag,
  origin TEXT NOT NULL CHECK (origin IN ('official','osm_tag','derived','first_party')),
  confidence TEXT NOT NULL CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
  last_verified_at DATE NOT NULL,
  PRIMARY KEY (restaurant_id, tag, origin)
);

CREATE TABLE enrichment.restaurant_opening_hours (
  hours_id BIGSERIAL PRIMARY KEY,
  restaurant_id UUID NOT NULL REFERENCES identity.restaurant ON DELETE CASCADE,
  raw_text TEXT NOT NULL, parsed JSONB,
  consistency TEXT NOT NULL CHECK (consistency IN ('agree','conflict','single_source')),
  source_id SMALLINT NOT NULL REFERENCES ref.data_source, source_url TEXT,
  confidence TEXT NOT NULL CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
  last_verified_at DATE NOT NULL,
  CONSTRAINT hours_unique UNIQUE (restaurant_id, source_id, raw_text)
);
CREATE INDEX hours_restaurant ON enrichment.restaurant_opening_hours (restaurant_id);

CREATE TABLE enrichment.restaurant_attribute_evidence (
  evidence_id    BIGSERIAL PRIMARY KEY,
  restaurant_id  UUID NOT NULL REFERENCES identity.restaurant ON DELETE CASCADE,
  attribute_code TEXT NOT NULL REFERENCES ref.attribute,
  state          ref.evidence_state NOT NULL,
  evidence_text  TEXT,
  evidence_basis TEXT NOT NULL REFERENCES ref.evidence_basis,
  applies_to     TEXT NOT NULL DEFAULT 'this_branch' CHECK (applies_to IN ('this_branch','brand_level','unknown')),
  source_id      SMALLINT NOT NULL REFERENCES ref.data_source,
  source_url     TEXT,
  confidence     TEXT NOT NULL CHECK (confidence IN ('HIGH','MEDIUM','LOW')),
  observed_at    DATE NOT NULL, last_verified_at DATE NOT NULL, valid_until DATE,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT evidence_dates      CHECK (observed_at <= last_verified_at AND (valid_until IS NULL OR valid_until >= last_verified_at)),
  CONSTRAINT evidence_confirmed_needs_high_this_branch CHECK (state NOT IN ('CONFIRMED_PRESENT','CONFIRMED_ABSENT') OR (confidence = 'HIGH' AND applies_to = 'this_branch')),
  CONSTRAINT evidence_absence_expires CHECK (state <> 'CONFIRMED_ABSENT' OR (valid_until IS NOT NULL AND valid_until <= last_verified_at + 180)),
  CONSTRAINT evidence_unique UNIQUE (restaurant_id, attribute_code, source_id, evidence_basis, applies_to)
);
CREATE INDEX evidence_lookup ON enrichment.restaurant_attribute_evidence (restaurant_id, attribute_code);

CREATE FUNCTION enrichment.evidence_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_first_party boolean; v_type text;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM ref.evidence_state_basis_rule WHERE state = NEW.state AND basis = NEW.evidence_basis) THEN
    RAISE EXCEPTION 'evidence basis % is not allowed for state %', NEW.evidence_basis, NEW.state USING ERRCODE = 'check_violation';
  END IF;
  SELECT is_first_party INTO v_first_party FROM ref.data_source WHERE source_id = NEW.source_id;
  IF NEW.state = 'CONFIRMED_ABSENT' AND NOT v_first_party THEN
    RAISE EXCEPTION 'CONFIRMED_ABSENT requires a first-party source (source_id %)', NEW.source_id USING ERRCODE = 'check_violation';
  END IF;
  SELECT attribute_type INTO v_type FROM ref.attribute WHERE attribute_code = NEW.attribute_code;
  IF NEW.state = 'CONFIRMED_PRESENT' AND NEW.evidence_basis = 'restaurant_name' AND v_type <> 'avoid' THEN
    RAISE EXCEPTION 'a restaurant name can confirm presence only for avoid-type attributes' USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER evidence_guard_trg BEFORE INSERT OR UPDATE ON enrichment.restaurant_attribute_evidence
  FOR EACH ROW EXECUTE FUNCTION enrichment.evidence_guard();

-- Evidence that may be used now: not expired, and test fixtures only when explicitly enabled for the session/transaction.
CREATE VIEW enrichment.v_evidence_valid AS
SELECT e.* FROM enrichment.restaurant_attribute_evidence e
JOIN ref.data_source s USING (source_id)
WHERE (e.valid_until IS NULL OR e.valid_until >= ref.today_tpe())
  AND (NOT s.is_test OR coalesce(current_setting('joeat.allow_test_evidence', true), 'off') = 'on');

-- Direct evidence plus implied evidence (shellfish => seafood ; vegan => vegetarian).
CREATE VIEW enrichment.v_evidence_expanded AS
SELECT e.evidence_id, e.restaurant_id, e.attribute_code, e.state, e.confidence, e.evidence_basis, e.last_verified_at, FALSE AS implied, NULL::text AS implied_from
FROM enrichment.v_evidence_valid e
UNION ALL
SELECT e.evidence_id, e.restaurant_id, i.super_attr, e.state, e.confidence, e.evidence_basis, e.last_verified_at, TRUE, e.attribute_code
FROM enrichment.v_evidence_valid e JOIN ref.attribute_implication i ON i.sub_attr = e.attribute_code
WHERE e.state IN ('CONFIRMED_PRESENT','LIKELY_PRESENT')
UNION ALL
SELECT e.evidence_id, e.restaurant_id, i.sub_attr, e.state, e.confidence, e.evidence_basis, e.last_verified_at, TRUE, e.attribute_code
FROM enrichment.v_evidence_valid e JOIN ref.attribute_implication i ON i.super_attr = e.attribute_code
WHERE e.state IN ('CONFIRMED_ABSENT','LIKELY_ABSENT');

-- Effective state per (restaurant, attribute). Conservative by attribute type:
--   avoid  : any presence evidence beats any absence evidence.
--   require: any absence evidence beats any presence evidence.
-- No row = UNKNOWN (consumers LEFT JOIN + COALESCE). deciding_evidence_id says which row decided; evidence_ids lists all valid ones.
CREATE VIEW enrichment.restaurant_attribute_state AS
WITH x AS (
  SELECT ev.*, a.attribute_type FROM enrichment.v_evidence_expanded ev JOIN ref.attribute a USING (attribute_code)
), agg AS (
  SELECT restaurant_id, attribute_code, attribute_type,
    (CASE attribute_type
       WHEN 'avoid' THEN CASE
         WHEN bool_or(state = 'CONFIRMED_PRESENT') THEN 'CONFIRMED_PRESENT'
         WHEN bool_or(state = 'LIKELY_PRESENT')    THEN 'LIKELY_PRESENT'
         WHEN bool_or(state = 'CONFIRMED_ABSENT')  THEN 'CONFIRMED_ABSENT'
         WHEN bool_or(state = 'LIKELY_ABSENT')     THEN 'LIKELY_ABSENT'
         ELSE 'UNKNOWN' END
       ELSE CASE
         WHEN bool_or(state = 'CONFIRMED_ABSENT')  THEN 'CONFIRMED_ABSENT'
         WHEN bool_or(state = 'LIKELY_ABSENT')     THEN 'LIKELY_ABSENT'
         WHEN bool_or(state = 'CONFIRMED_PRESENT') THEN 'CONFIRMED_PRESENT'
         WHEN bool_or(state = 'LIKELY_PRESENT')    THEN 'LIKELY_PRESENT'
         ELSE 'UNKNOWN' END
     END)::ref.evidence_state AS state,
    array_agg(DISTINCT evidence_id) AS evidence_ids, max(last_verified_at) AS last_verified_at
  FROM x GROUP BY restaurant_id, attribute_code, attribute_type
)
SELECT agg.restaurant_id, agg.attribute_code, agg.state, d.evidence_id AS deciding_evidence_id, d.implied, d.implied_from,
       agg.evidence_ids, agg.last_verified_at
FROM agg
LEFT JOIN LATERAL (
  SELECT x.evidence_id, x.implied, x.implied_from FROM x
  WHERE x.restaurant_id = agg.restaurant_id AND x.attribute_code = agg.attribute_code AND x.state = agg.state
  ORDER BY (x.confidence = 'HIGH') DESC, x.implied, x.last_verified_at DESC, x.evidence_id LIMIT 1
) d ON TRUE;

-- Identity corroboration used by the "data confidence" score component: independent source types with a settled link.
CREATE VIEW identity.v_restaurant_corroboration AS
SELECT r.restaurant_id,
       count(DISTINCT se.source_id) FILTER (WHERE se.match_status IN ('auto','manual_confirmed')) AS settled_source_count
FROM identity.restaurant r LEFT JOIN identity.restaurant_source_entity se USING (restaurant_id)
GROUP BY r.restaurant_id;

-- Deferred until the data exists and the licence is cleared (columns/components already reserved in product.*):
--   enrichment.restaurant_rating_snapshot, enrichment.restaurant_price_signal, enrichment.restaurant_group_feature

-- ===================================================================== product
CREATE TABLE product.dining_session (
  session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  line_group_ref TEXT,                              -- hashed; never the raw LINE group id
  area TEXT NOT NULL DEFAULT '鹽埕區',
  meeting_lat DOUBLE PRECISION, meeting_lon DOUBLE PRECISION, radius_m INTEGER CHECK (radius_m IS NULL OR radius_m > 0),
  meal_time TIMESTAMPTZ,
  party_size SMALLINT,
  status TEXT NOT NULL DEFAULT 'collecting' CHECK (status IN ('collecting','recommended','closed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days'),
  CONSTRAINT session_party_size CHECK (party_size IS NULL OR party_size BETWEEN 2 AND 10),
  CONSTRAINT session_meeting_pair CHECK ((meeting_lat IS NULL) = (meeting_lon IS NULL)),
  CONSTRAINT session_expiry CHECK (expires_at > created_at)
);
CREATE INDEX session_expiry ON product.dining_session (expires_at);

CREATE TABLE product.participant (
  participant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES product.dining_session ON DELETE CASCADE,
  line_user_ref TEXT NOT NULL,                      -- hashed LINE user id
  label TEXT,                                       -- short UI label ('A', nickname); do not store real names
  submitted_at TIMESTAMPTZ,
  CONSTRAINT participant_unique_user UNIQUE (session_id, line_user_ref),
  CONSTRAINT participant_session_key UNIQUE (participant_id, session_id)
);

CREATE TABLE product.participant_hard_constraint (
  participant_id UUID NOT NULL REFERENCES product.participant ON DELETE CASCADE,
  attribute_code TEXT NOT NULL REFERENCES ref.attribute,
  reason TEXT NOT NULL DEFAULT 'unspecified' REFERENCES ref.constraint_reason,
  PRIMARY KEY (participant_id, attribute_code)
);

CREATE TABLE product.participant_budget (           -- SOFT ONLY: never used to exclude. Per-person prices are not reliably available yet.
  participant_id UUID PRIMARY KEY REFERENCES product.participant ON DELETE CASCADE,
  max_per_person INTEGER NOT NULL CHECK (max_per_person > 0)
);

CREATE TABLE product.participant_preference (
  participant_id UUID NOT NULL REFERENCES product.participant ON DELETE CASCADE,
  cuisine_tag TEXT NOT NULL REFERENCES ref.cuisine_tag,
  stance TEXT NOT NULL CHECK (stance IN ('love','ok','any','dislike')),   -- 很想吃 / 可以 / 都好 / 不太想
  PRIMARY KEY (participant_id, cuisine_tag)
);

CREATE TABLE product.recommendation_run (
  run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES product.dining_session ON DELETE CASCADE,
  scoring_version TEXT NOT NULL REFERENCES ref.scoring_config,
  config_snapshot JSONB NOT NULL,                  -- exact weights used, so old runs stay explainable
  data_snapshot_at TIMESTAMPTZ NOT NULL,
  pool_size INTEGER, excluded_count INTEGER, eligible_count INTEGER,
  completed_at TIMESTAMPTZ,                         -- NULL while running; set when scoring and ranking are done
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT run_session_key UNIQUE (run_id, session_id)
);
CREATE INDEX run_session ON product.recommendation_run (session_id);

CREATE TABLE product.recommendation_candidate (
  run_id UUID NOT NULL REFERENCES product.recommendation_run ON DELETE CASCADE,
  restaurant_id UUID NOT NULL REFERENCES identity.restaurant,
  stage TEXT NOT NULL CHECK (stage IN ('excluded','eligible','top3')),
  distance_m INTEGER,
  cuisine_score     NUMERIC(6,2), distance_score NUMERIC(6,2), data_confidence_score NUMERIC(6,2),
  rating_score      NUMERIC(6,2),                  -- reserved: NULL until a rating source is validated
  total_score       NUMERIC(7,2),
  rank              SMALLINT,
  warning_count INTEGER NOT NULL DEFAULT 0, critical_warning_count INTEGER NOT NULL DEFAULT 0,
  warnings JSONB NOT NULL DEFAULT '[]'::jsonb,     -- non-attribute notes: hours_unknown, price_unknown, distance_unknown ...
  explanation JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (run_id, restaurant_id),
  CONSTRAINT cand_excluded_unscored CHECK (stage <> 'excluded' OR (total_score IS NULL AND rank IS NULL)),
  CONSTRAINT cand_eligible_unranked CHECK (stage <> 'eligible' OR rank IS NULL),   -- scored in later steps of evaluate_session; completed runs are verified by schema_tests.py
  CONSTRAINT cand_top3_ranked       CHECK (stage <> 'top3' OR (total_score IS NOT NULL AND rank BETWEEN 1 AND 3))
);
CREATE UNIQUE INDEX cand_unique_rank ON product.recommendation_candidate (run_id, rank) WHERE rank IS NOT NULL;
CREATE INDEX cand_restaurant ON product.recommendation_candidate (restaurant_id);

CREATE TABLE product.recommendation_constraint_check (    -- one row per (restaurant, participant, attribute): the audit trail behind every exclusion/warning
  check_id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL, session_id UUID NOT NULL, restaurant_id UUID NOT NULL, participant_id UUID NOT NULL,
  attribute_code TEXT NOT NULL REFERENCES ref.attribute,
  attribute_type TEXT NOT NULL, effective_risk_level TEXT NOT NULL CHECK (effective_risk_level IN ('critical','high','normal')),
  evidence_state ref.evidence_state NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('PASS','PASS_CONDITIONAL','WARN','EXCLUDE')),
  warning_level TEXT NOT NULL CHECK (warning_level IN ('none','normal','high','critical')),
  may_show_safe_badge BOOLEAN NOT NULL DEFAULT FALSE,
  deciding_evidence_id BIGINT REFERENCES enrichment.restaurant_attribute_evidence ON DELETE SET NULL,
  evidence_snapshot JSONB,                          -- copy of the deciding evidence (text, basis, source, confidence, dates)
  message_zh TEXT,
  CONSTRAINT chk_unique UNIQUE (run_id, restaurant_id, participant_id, attribute_code),
  CONSTRAINT chk_run_fk  FOREIGN KEY (run_id, session_id) REFERENCES product.recommendation_run (run_id, session_id) ON DELETE CASCADE,
  CONSTRAINT chk_cand_fk FOREIGN KEY (run_id, restaurant_id) REFERENCES product.recommendation_candidate (run_id, restaurant_id) ON DELETE CASCADE,
  CONSTRAINT chk_part_fk FOREIGN KEY (participant_id, session_id) REFERENCES product.participant (participant_id, session_id) ON DELETE CASCADE   -- cascade from both parents: session delete must not depend on trigger order
);
CREATE INDEX chk_by_candidate ON product.recommendation_constraint_check (run_id, restaurant_id);
CREATE INDEX chk_by_participant ON product.recommendation_constraint_check (participant_id);
CREATE INDEX chk_by_evidence ON product.recommendation_constraint_check (deciding_evidence_id) WHERE deciding_evidence_id IS NOT NULL;

CREATE TABLE product.recommendation_score_component (
  component_id BIGSERIAL PRIMARY KEY,
  run_id UUID NOT NULL, session_id UUID NOT NULL, restaurant_id UUID NOT NULL,
  component TEXT NOT NULL CHECK (component IN ('cuisine_preference','distance','data_confidence','rating','price')),
  participant_id UUID,                              -- only for per-participant components (cuisine_preference)
  raw_value TEXT, points NUMERIC(6,2) NOT NULL DEFAULT 0, detail JSONB,
  CONSTRAINT comp_cand_fk FOREIGN KEY (run_id, restaurant_id) REFERENCES product.recommendation_candidate (run_id, restaurant_id) ON DELETE CASCADE,
  CONSTRAINT comp_part_fk FOREIGN KEY (participant_id, session_id) REFERENCES product.participant (participant_id, session_id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX comp_unique ON product.recommendation_score_component
  (run_id, restaurant_id, component, COALESCE(participant_id, '00000000-0000-0000-0000-000000000000'::uuid));
CREATE INDEX comp_by_candidate ON product.recommendation_score_component (run_id, restaurant_id);
CREATE INDEX comp_by_participant ON product.recommendation_score_component (participant_id) WHERE participant_id IS NOT NULL;

-- Everything the UI needs to answer "why this restaurant?" and "what do we not know?"
CREATE VIEW product.v_recommendation_explanation AS
SELECT c.run_id, c.restaurant_id, r.canonical_name, c.stage, c.rank, c.total_score, c.distance_m,
       c.cuisine_score, c.distance_score, c.data_confidence_score, c.rating_score,
       (SELECT coalesce(jsonb_agg(jsonb_build_object('component', s.component, 'participant_id', s.participant_id, 'points', s.points, 'raw', s.raw_value, 'detail', s.detail)
                ORDER BY s.component, s.participant_id), '[]'::jsonb)
          FROM product.recommendation_score_component s WHERE s.run_id = c.run_id AND s.restaurant_id = c.restaurant_id) AS components,
       (SELECT coalesce(jsonb_agg(jsonb_build_object('participant_id', k.participant_id, 'attribute', k.attribute_code, 'state', k.evidence_state,
                'action', k.action, 'warning_level', k.warning_level, 'message', k.message_zh, 'evidence', k.evidence_snapshot)
                ORDER BY (CASE k.warning_level WHEN 'critical' THEN 3 WHEN 'high' THEN 2 WHEN 'normal' THEN 1 ELSE 0 END) DESC, k.attribute_code), '[]'::jsonb)   -- critical first (NOT alphabetical)
          FROM product.recommendation_constraint_check k
          WHERE k.run_id = c.run_id AND k.restaurant_id = c.restaurant_id AND k.action IN ('WARN','PASS_CONDITIONAL','EXCLUDE')) AS constraint_notes,
       c.warnings
FROM product.recommendation_candidate c JOIN identity.restaurant r USING (restaurant_id);

-- ===================================================================== engine v1 (deterministic, no ML)
-- evaluate_session(): 1) pool  2) hard-constraint checks (rule table)  3) exclude  4) score  5) rank  6) top3.  Everything it decides is stored.
CREATE FUNCTION product.evaluate_session(p_session UUID, p_version TEXT DEFAULT NULL) RETURNS UUID
LANGUAGE plpgsql AS $$
DECLARE
  v_run UUID := gen_random_uuid(); v_cfg JSONB; v_ver TEXT; v_sess product.dining_session%ROWTYPE; v_top INT;
BEGIN
  SELECT * INTO v_sess FROM product.dining_session WHERE session_id = p_session;
  IF NOT FOUND THEN RAISE EXCEPTION 'session % not found', p_session; END IF;
  SELECT version, config INTO v_ver, v_cfg FROM ref.scoring_config WHERE (p_version IS NULL AND is_active) OR version = p_version LIMIT 1;
  IF v_cfg IS NULL THEN RAISE EXCEPTION 'no scoring config'; END IF;
  v_top := coalesce((v_cfg ->> 'top_n')::int, 3);
  INSERT INTO product.recommendation_run (run_id, session_id, scoring_version, config_snapshot, data_snapshot_at)
  VALUES (v_run, p_session, v_ver, v_cfg, now());

  CREATE TEMP TABLE _pool ON COMMIT DROP AS
  SELECT r.restaurant_id, r.lat, r.lon,
         CASE WHEN v_sess.meeting_lat IS NOT NULL AND r.lat IS NOT NULL
              THEN round(ref.haversine_m(v_sess.meeting_lat, v_sess.meeting_lon, r.lat, r.lon))::int END AS distance_m
  FROM identity.restaurant r
  WHERE r.pool_status = 'in_pool' AND r.active_status IN ('active','unverified') AND r.merged_into_restaurant_id IS NULL AND r.district = v_sess.area;

  CREATE TEMP TABLE _checks ON COMMIT DROP AS
  SELECT p.restaurant_id, pa.participant_id, hc.attribute_code, a.attribute_type,
         CASE WHEN ref.risk_rank(cr.min_risk_level) > ref.risk_rank(a.risk_level) THEN cr.min_risk_level ELSE a.risk_level END AS eff_risk,
         coalesce(s.state, 'UNKNOWN'::ref.evidence_state) AS state, s.deciding_evidence_id, a.display_name_zh
  FROM _pool p
  CROSS JOIN product.participant pa
  JOIN product.participant_hard_constraint hc ON hc.participant_id = pa.participant_id
  JOIN ref.attribute a ON a.attribute_code = hc.attribute_code
  JOIN ref.constraint_reason cr ON cr.reason = hc.reason
  LEFT JOIN enrichment.restaurant_attribute_state s ON s.restaurant_id = p.restaurant_id AND s.attribute_code = hc.attribute_code
  WHERE pa.session_id = p_session;

  CREATE TEMP TABLE _excluded ON COMMIT DROP AS
  SELECT DISTINCT c.restaurant_id FROM _checks c
  JOIN ref.constraint_decision_rule d ON d.attribute_type = c.attribute_type AND d.risk_level = c.eff_risk AND d.state = c.state
  WHERE d.action = 'EXCLUDE';

  INSERT INTO product.recommendation_candidate (run_id, restaurant_id, stage, distance_m)
  SELECT v_run, p.restaurant_id, CASE WHEN e.restaurant_id IS NULL THEN 'eligible' ELSE 'excluded' END, p.distance_m
  FROM _pool p LEFT JOIN _excluded e USING (restaurant_id);

  INSERT INTO product.recommendation_constraint_check
    (run_id, session_id, restaurant_id, participant_id, attribute_code, attribute_type, effective_risk_level, evidence_state, action, warning_level,
     may_show_safe_badge, deciding_evidence_id, evidence_snapshot, message_zh)
  SELECT v_run, p_session, c.restaurant_id, c.participant_id, c.attribute_code, c.attribute_type, c.eff_risk, c.state, d.action, d.warning_level,
         d.may_show_safe_badge, c.deciding_evidence_id,
         (SELECT jsonb_build_object('text', e.evidence_text, 'basis', e.evidence_basis, 'applies_to', e.applies_to, 'confidence', e.confidence,
                 'source_id', e.source_id, 'source_url', e.source_url, 'last_verified_at', e.last_verified_at)
            FROM enrichment.restaurant_attribute_evidence e WHERE e.evidence_id = c.deciding_evidence_id),
         CASE d.action
           WHEN 'EXCLUDE' THEN c.display_name_zh || '：此店' || CASE WHEN c.attribute_type = 'avoid' THEN '含有/疑似含有' ELSE '不符合' END
           WHEN 'PASS'    THEN c.display_name_zh || '：' || CASE WHEN d.may_show_safe_badge THEN '已有第一手資料確認符合' ELSE '符合' END
           WHEN 'PASS_CONDITIONAL' THEN c.display_name_zh || '：可能符合，但未經店家確認'
           ELSE c.display_name_zh || '：資料不足，無法確認，請向店家確認' END
  FROM _checks c JOIN ref.constraint_decision_rule d
    ON d.attribute_type = c.attribute_type AND d.risk_level = c.eff_risk AND d.state = c.state;

  -- score components (eligible only)
  INSERT INTO product.recommendation_score_component (run_id, session_id, restaurant_id, component, participant_id, raw_value, points, detail)
  SELECT v_run, p_session, cand.restaurant_id, 'cuisine_preference', pa.participant_id,
         m.stance, coalesce(m.pts, 0), jsonb_build_object('matched_tag', m.cuisine_tag)
  FROM product.recommendation_candidate cand
  CROSS JOIN product.participant pa
  LEFT JOIN LATERAL (
    SELECT pp.stance, pp.cuisine_tag, (v_cfg -> 'cuisine_stance_points' ->> pp.stance)::numeric AS pts
    FROM product.participant_preference pp
    JOIN enrichment.restaurant_cuisine rc ON rc.restaurant_id = cand.restaurant_id
    JOIN ref.cuisine_tag ct ON ct.tag = rc.tag
    WHERE pp.participant_id = pa.participant_id AND (pp.cuisine_tag = ct.tag OR pp.cuisine_tag = ct.parent_tag)
    ORDER BY (v_cfg -> 'cuisine_stance_points' ->> pp.stance)::numeric DESC LIMIT 1
  ) m ON TRUE
  WHERE cand.run_id = v_run AND cand.stage = 'eligible' AND pa.session_id = p_session;

  INSERT INTO product.recommendation_score_component (run_id, session_id, restaurant_id, component, raw_value, points, detail)
  SELECT v_run, p_session, cand.restaurant_id, 'distance', cand.distance_m::text,
         CASE WHEN cand.distance_m IS NULL THEN 0   -- unknown distance is neutral (0 points + a warning), NOT the "farther than everything" band
              ELSE coalesce((SELECT (b ->> 'points')::numeric FROM jsonb_array_elements(v_cfg -> 'distance_bands_m') b
                    WHERE (b ->> 'max') IS NULL OR cand.distance_m <= (b ->> 'max')::int ORDER BY (b ->> 'max')::int NULLS LAST LIMIT 1), 0) END,
         jsonb_build_object('state', CASE WHEN cand.distance_m IS NULL THEN 'UNKNOWN' ELSE 'known' END)
  FROM product.recommendation_candidate cand WHERE cand.run_id = v_run AND cand.stage = 'eligible';

  INSERT INTO product.recommendation_score_component (run_id, session_id, restaurant_id, component, raw_value, points, detail)
  SELECT v_run, p_session, cand.restaurant_id, 'data_confidence', co.settled_source_count::text,
         CASE WHEN co.settled_source_count >= 2 THEN (v_cfg -> 'data_confidence' ->> 'multi_source_points')::numeric ELSE 0 END,
         jsonb_build_object('rule', 'points only when >=2 independent sources are settled; missing data adds nothing')
  FROM product.recommendation_candidate cand JOIN identity.v_restaurant_corroboration co USING (restaurant_id)
  WHERE cand.run_id = v_run AND cand.stage = 'eligible';

  INSERT INTO product.recommendation_score_component (run_id, session_id, restaurant_id, component, raw_value, points, detail)
  SELECT v_run, p_session, cand.restaurant_id, k.component, 'UNKNOWN', 0,
         jsonb_build_object('state', 'UNKNOWN', 'note', k.note)
  FROM product.recommendation_candidate cand
  CROSS JOIN (VALUES ('rating', 'no validated rating source'), ('price', 'no per-person price data; budget is soft only')) AS k(component, note)
  WHERE cand.run_id = v_run AND cand.stage = 'eligible';

  -- warnings that are not attribute checks
  UPDATE product.recommendation_candidate cand SET warnings = w.warnings
  FROM (
    SELECT cand2.restaurant_id,
      (CASE WHEN cand2.distance_m IS NULL THEN jsonb_build_array(jsonb_build_object('code','distance_unknown','level','normal')) ELSE '[]'::jsonb END) ||
      (CASE WHEN NOT EXISTS (SELECT 1 FROM enrichment.restaurant_opening_hours h WHERE h.restaurant_id = cand2.restaurant_id)
            THEN jsonb_build_array(jsonb_build_object('code','hours_unknown','level','normal'))
            WHEN EXISTS (SELECT 1 FROM enrichment.restaurant_opening_hours h WHERE h.restaurant_id = cand2.restaurant_id AND h.consistency = 'conflict')
            THEN jsonb_build_array(jsonb_build_object('code','hours_conflict','level','normal')) ELSE '[]'::jsonb END) ||
      (CASE WHEN EXISTS (SELECT 1 FROM product.participant_budget b JOIN product.participant pa USING (participant_id) WHERE pa.session_id = p_session)
            THEN jsonb_build_array(jsonb_build_object('code','price_unknown','level','normal')) ELSE '[]'::jsonb END) AS warnings
    FROM product.recommendation_candidate cand2 WHERE cand2.run_id = v_run
  ) w WHERE cand.run_id = v_run AND cand.restaurant_id = w.restaurant_id;

  UPDATE product.recommendation_candidate cand SET
    cuisine_score = (SELECT coalesce(sum(points), 0) FROM product.recommendation_score_component s WHERE s.run_id = cand.run_id AND s.restaurant_id = cand.restaurant_id AND s.component = 'cuisine_preference'),
    distance_score = (SELECT coalesce(sum(points), 0) FROM product.recommendation_score_component s WHERE s.run_id = cand.run_id AND s.restaurant_id = cand.restaurant_id AND s.component = 'distance'),
    data_confidence_score = (SELECT coalesce(sum(points), 0) FROM product.recommendation_score_component s WHERE s.run_id = cand.run_id AND s.restaurant_id = cand.restaurant_id AND s.component = 'data_confidence')
  WHERE cand.run_id = v_run AND cand.stage = 'eligible';

  UPDATE product.recommendation_candidate cand SET
    total_score = cuisine_score + distance_score + data_confidence_score + coalesce(rating_score, 0),
    warning_count = (SELECT count(*) FROM product.recommendation_constraint_check k WHERE k.run_id = cand.run_id AND k.restaurant_id = cand.restaurant_id AND k.action IN ('WARN','PASS_CONDITIONAL'))
                    + jsonb_array_length(cand.warnings),
    critical_warning_count = (SELECT count(*) FROM product.recommendation_constraint_check k WHERE k.run_id = cand.run_id AND k.restaurant_id = cand.restaurant_id AND k.action IN ('WARN','PASS_CONDITIONAL') AND k.warning_level = 'critical')
  WHERE cand.run_id = v_run AND cand.stage = 'eligible';

  -- rank: score desc, fewer critical warnings, fewer warnings, nearer, stable id
  UPDATE product.recommendation_candidate cand SET stage = 'top3', rank = t.rn
  FROM (SELECT restaurant_id, row_number() OVER (ORDER BY total_score DESC, critical_warning_count, warning_count, distance_m NULLS LAST, restaurant_id) AS rn
        FROM product.recommendation_candidate WHERE run_id = v_run AND stage = 'eligible') t
  WHERE cand.run_id = v_run AND cand.restaurant_id = t.restaurant_id AND t.rn <= v_top;

  UPDATE product.recommendation_candidate cand SET explanation = jsonb_build_object(
      'summary_zh', '總分 ' || coalesce(total_score::text, '-') || '：料理偏好 ' || coalesce(cuisine_score::text, '0') || '、距離 ' || coalesce(distance_score::text, '0')
                    || '、資料可信度 ' || coalesce(data_confidence_score::text, '0') || '；評價與價格尚無可靠資料，未計分',
      'unknown_attributes', (SELECT coalesce(jsonb_agg(DISTINCT k.attribute_code), '[]'::jsonb) FROM product.recommendation_constraint_check k
                              WHERE k.run_id = cand.run_id AND k.restaurant_id = cand.restaurant_id AND k.evidence_state IN ('UNKNOWN','LIKELY_ABSENT')))
  WHERE cand.run_id = v_run AND cand.stage <> 'excluded';

  UPDATE product.recommendation_run SET
    pool_size = (SELECT count(*) FROM product.recommendation_candidate WHERE run_id = v_run),
    excluded_count = (SELECT count(*) FROM product.recommendation_candidate WHERE run_id = v_run AND stage = 'excluded'),
    eligible_count = (SELECT count(*) FROM product.recommendation_candidate WHERE run_id = v_run AND stage <> 'excluded')
    , completed_at = now()
  WHERE run_id = v_run;

  DROP TABLE _pool; DROP TABLE _checks; DROP TABLE _excluded;
  UPDATE product.dining_session SET status = 'recommended' WHERE session_id = p_session;
  RETURN v_run;
END $$;
