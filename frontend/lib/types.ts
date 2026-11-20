// Mirrors the backend response models (see API.md). Nothing here ever carries another participant's constraints.
export type Stance = "love" | "ok" | "any" | "dislike";

export interface Session {
  session_id: string;
  title: string | null;
  area: string;
  location_label: string | null;
  meeting_lat: number | null;
  meeting_lon: number | null;
  meal_time: string | null;
  party_size: number | null;
  status: string;
  participant_count: number;
  expires_at: string;
  time_mode: "fixed" | "poll";
  time_deadline: string | null;
  time_closed: boolean;
  outside_coverage: boolean;          // the meeting point is far from 鹽埕區, the only area with restaurant data
  needs_pets: boolean;                // the host said someone brings a pet
  needs_kids: boolean;                // ... a child
}

/** How one restaurant fits a group need. yes / maybe = fits (confirmed / not confirmed), no = it says it does not, unknown = no data. */
export interface Need { code: "pets" | "kids"; name: string; status: "yes" | "maybe" | "no" | "unknown"; text: string }

export interface Participant {
  participant_id: string;
  session_id: string;
  label: string | null;
  constraints_submitted: boolean;
  preferences_submitted: boolean;
  is_host: boolean;
}

/** What a participant has saved (read back so the forms can be edited). */
export interface Answers {
  constraints: { attribute_code: string; reason: string }[];
  strict_allergy: boolean;
  budget_max_per_person: number | null;
  preferences: { cuisine_tag: string; stance: Stance }[];
  diet_type: string | null;
  constraints_submitted: boolean;
  preferences_submitted: boolean;
}

/** Dining type ("飲食 MBTI"): fun + a preference shortcut. It never changes the recommendation. */
export interface DietType { code: string; emoji: string; name: string; summary: string; suggested_cuisines: string[] }
export interface DietMeta {
  questions: { id: string; axis: string; text: string; options: { value: string; label: string }[] }[];
  types: DietType[];
  axes: { key: string; a: { letter: string; label: string }; b: { letter: string; label: string } }[];
}
export interface DietComposition {
  hidden: boolean;
  taken: number;
  joined: number;
  types: { code: string; emoji: string; name: string; count: number }[];
  axes: { key: string; a: { label: string; count: number }; b: { label: string; count: number } }[];
}

export interface TimePoll {
  session_id: string;
  closed: boolean;
  deadline: string | null;
  meal_time: string | null;
  chosen_option_id: number | null;
  responded: number;
  joined: number;
  party_size: number | null;
  options: { option_id: number; starts_at: string; count: number; mine: boolean }[];
}

export interface VoteOption {
  restaurant_id: string;
  rank: number;
  name: string;
  address: string | null;
  cuisines: string[];
  distance_m: number | null;
  warnings: { level: string; text: string }[];
  declarations: { display: string; text: string; verified: boolean }[];
  needs: { name: string; status: string; text: string }[];
  my_score: number | null;
  my_any_ok: boolean;
}
export interface Vote {
  vote_id: string;
  status: "open" | "closed";
  closes_at: string;
  voted: number;
  joined: number;
  i_voted: boolean;
  options: VoteOption[];
  result: { restaurant_id: string; name: string; total: number; average: number | null; voters: number; unhappy: number; keen: number; any_ok: number }[] | null;
  winner_restaurant_id: string | null;
  tie_broken: boolean;
}

export interface Progress {
  session_id: string;
  party_size: number | null;
  joined: number;
  constraints_done: number;
  preferences_done: number;
  participants: { label: string | null; is_me: boolean; constraints_done: boolean; preferences_done: boolean }[];
  all_complete: boolean;
  ready_for_recommendation: boolean;
  missing_count: number;
}

export interface AttributeItem {
  attribute_code: string;
  label: string;
  type: "avoid" | "require";
  risk_level: "critical" | "high" | "normal";
  description: string;
}
export interface AttributeMeta {
  groups: { key: string; label: string; items: AttributeItem[] }[];
  reasons: { reason: string; label: string }[];
  privacy_note: string;
}
export interface CuisineMeta {
  chips: { tag: string; label: string }[];
  stances: { stance: Stance; label: string }[];
}
export interface LocationPreset { key: string; label: string; lat: number; lon: number }

export interface Warning { code: string; level: "critical" | "high" | "normal"; text: string; attribute?: string | null; display?: string | null }

export interface RestaurantRecommendation {
  rank: number;
  restaurant_id: string;
  name: string;
  address: string | null;
  phone: string | null;
  cuisines: string[];
  distance_m: number | null;
  score: { cuisine: number; distance: number; data_confidence: number; rating: number | null; total: number };
  hard_constraint: { status: "no_constraints" | "no_known_conflict" | "partial_conflict" | "suspected_conflict"; unknown_attributes: string[]; confirmed_safe: string[]; note: string };
  warnings: Warning[];
  reasons: string[];
  summary: string;
  declarations: Declaration[];
  needs: Need[];
}

/** A merchant's dated statement of fact (never a safety claim). `verified` = a reviewer verified the claimant by a strong method. */
export interface Declaration { attribute: string; display: string; text: string; verified: boolean }

export interface Recommendation {
  run_id: string;
  session_id: string;
  created_at: string;
  scoring_version: string;
  participants: number;
  party_size: number | null;
  pool_size: number;
  excluded_count: number;
  eligible_count: number;
  top3: RestaurantRecommendation[];
  test_evidence_enabled: boolean;
  strict_mode: boolean;
  excluded: { restaurant_id: string; name: string; reasons: string[] }[] | null;
  disclaimer: string;
}
