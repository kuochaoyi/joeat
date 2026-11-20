-- 0009: group needs chosen by the host - "someone is bringing a pet / a child".
-- They are SESSION-level (public to the group, not any member's private constraint) and become two extra checks in every recommendation:
--   pets_allowed  (require): a restaurant that explicitly does not allow pets is excluded; unknown is only a warning
--   kid_friendly  (require): only ever a warning (a restaurant without a high chair may still welcome children)
-- The two attributes themselves live in the attribute dictionary (data/seed/01_attribute_seed.sql), like every other attribute.
ALTER TABLE product.dining_session
  ADD COLUMN needs_pets BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN needs_kids BOOLEAN NOT NULL DEFAULT FALSE;
