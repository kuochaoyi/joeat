-- 0005: recommendation integration.
--  * product.participant.strict_allergy : a member opts in to "strict allergy mode" (only restaurants with a confirmed absence pass their safety constraints)
--  * product.restaurant_report          : "report a mistake" queue. A report NEVER changes data by itself; a reviewer dismisses it or escalates it to an incident.

ALTER TABLE product.participant ADD COLUMN strict_allergy BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE product.restaurant_report (
  report_id     BIGSERIAL PRIMARY KEY,
  restaurant_id UUID NOT NULL REFERENCES identity.restaurant(restaurant_id),
  attribute_code TEXT REFERENCES ref.attribute(attribute_code),
  participant_id UUID REFERENCES product.participant(participant_id) ON DELETE SET NULL,   -- who reported: only used for rate limiting, never shown to reviewers
  kind          TEXT NOT NULL CHECK (kind IN ('wrong_info','allergic_reaction','closed','other')),
  note          TEXT CHECK (note IS NULL OR length(note) <= 300),
  status        TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','dismissed','escalated')),
  incident_id   BIGINT REFERENCES merchant.incident_report(incident_id),
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  handled_by    TEXT,
  handled_at    TIMESTAMPTZ,
  handled_note  TEXT,
  CHECK ((status = 'open') = (handled_at IS NULL)),
  CHECK (status <> 'escalated' OR incident_id IS NOT NULL)
);
CREATE INDEX report_participant_time ON product.restaurant_report (participant_id, created_at);
CREATE INDEX report_status ON product.restaurant_report (status, created_at);
