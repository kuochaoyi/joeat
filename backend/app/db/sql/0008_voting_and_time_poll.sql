-- 0008: user-testing feedback.
--  * party size up to 20 (was 2-10)
--  * a session knows its host (hashed, like every other LINE id): the host sets deadlines and may close polls early
--  * time poll: members tick the slots they can make; the host only sets the deadline (feedback: "time should be chosen by everyone, not the host")
--  * restaurant vote: each member moves a slider (0-10, or "any is fine") for every Top-3 restaurant; nobody sees who voted what

ALTER TABLE product.dining_session DROP CONSTRAINT session_party_size;
ALTER TABLE product.dining_session ADD CONSTRAINT session_party_size CHECK (party_size IS NULL OR party_size BETWEEN 2 AND 20);

ALTER TABLE product.dining_session
  ADD COLUMN host_ref TEXT,                                                    -- HMAC of the creator's LINE user id; NULL = created from the LINE bot (no host powers)
  ADD COLUMN time_mode TEXT NOT NULL DEFAULT 'fixed' CHECK (time_mode IN ('fixed', 'poll')),
  ADD COLUMN time_deadline TIMESTAMPTZ,
  ADD COLUMN time_closed_at TIMESTAMPTZ;

CREATE TABLE product.time_option (
  option_id  BIGSERIAL PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES product.dining_session(session_id),
  starts_at  TIMESTAMPTZ NOT NULL,
  UNIQUE (session_id, starts_at)
);
CREATE TABLE product.time_response (
  option_id      BIGINT NOT NULL REFERENCES product.time_option(option_id),
  participant_id UUID   NOT NULL REFERENCES product.participant(participant_id),
  PRIMARY KEY (option_id, participant_id)
);

CREATE TABLE product.vote (
  vote_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id UUID NOT NULL REFERENCES product.dining_session(session_id),
  run_id     UUID NOT NULL REFERENCES product.recommendation_run(run_id),
  status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
  closes_at  TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  closed_at  TIMESTAMPTZ,
  winner_restaurant_id UUID REFERENCES identity.restaurant(restaurant_id),
  tie_broken BOOLEAN NOT NULL DEFAULT FALSE,
  CHECK ((status = 'closed') = (closed_at IS NOT NULL))
);
CREATE INDEX vote_session ON product.vote (session_id, created_at DESC);
CREATE TABLE product.vote_option (
  vote_id       UUID NOT NULL REFERENCES product.vote(vote_id),
  restaurant_id UUID NOT NULL REFERENCES identity.restaurant(restaurant_id),
  rank          SMALLINT NOT NULL,                                            -- the recommendation rank: breaks a tie
  snapshot      JSONB NOT NULL,                                               -- the card shown to voters (name, warnings, declarations) frozen at vote start
  PRIMARY KEY (vote_id, restaurant_id)
);
CREATE TABLE product.vote_ballot (
  vote_id        UUID NOT NULL,
  participant_id UUID NOT NULL REFERENCES product.participant(participant_id),
  restaurant_id  UUID NOT NULL,
  score          SMALLINT NOT NULL CHECK (score BETWEEN 0 AND 10),             -- 0 = would rather not, 10 = really want to
  any_ok         BOOLEAN NOT NULL DEFAULT FALSE,                              -- "anything is fine": stored as the neutral score 5
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (vote_id, participant_id, restaurant_id),
  FOREIGN KEY (vote_id, restaurant_id) REFERENCES product.vote_option(vote_id, restaurant_id),
  CHECK (NOT any_ok OR score = 5)
);
