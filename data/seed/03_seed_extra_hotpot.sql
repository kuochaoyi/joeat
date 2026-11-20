-- 03_seed_extra_hotpot.sql : one extra REAL restaurant so the demo can show a hotpot cuisine bonus from a corroborated shop.
-- Sources (both real, both from the PoC): (1) tax registry row 57942430 "天天沙茶火鍋" (sole proprietorship, registered 2006-12-19, 七賢三路240號,
-- industry 561113); (2) a 2026-10-31 web-search result that names "汕頭天天沙茶火鍋" at 七賢三路240號 (the exact page was not identified, so no URL).
-- A second, newer registration (62168762, 天天沙茶火鍋有限公司, 七賢三路244之1號, 2026-08-07) is kept unresolved for human review (move / expansion / branch?).
-- No coordinates are known -> distance stays UNKNOWN for this shop. active_status stays unverified.
BEGIN;
INSERT INTO identity.restaurant (restaurant_id, canonical_name, canonical_address, address_key, district, city, active_status, pool_status)
VALUES ('04a1e31e-4791-5216-ae15-73811d7b60ca', '汕頭天天沙茶火鍋', '高雄市鹽埕區七賢三路240號', '七賢三路|240|', '鹽埕區', '高雄市', 'unverified', 'in_pool');
INSERT INTO identity.restaurant_source_entity (restaurant_id, source_id, source_record_id, source_name, source_address, address_key, industry_code, matched_by, er_version, match_status, first_seen_at, last_seen_at)
VALUES ('04a1e31e-4791-5216-ae15-73811d7b60ca', 1, '57942430|高雄市鹽埕區府北里七賢三路２４０號１樓', '天天沙茶火鍋', '高雄市鹽埕區府北里七賢三路２４０號１樓', '七賢三路|240|', '561113', 'same_address+name', 'v0-manual-check', 'auto', '2026-10-31', '2026-10-31');
INSERT INTO identity.restaurant_source_entity (restaurant_id, source_id, source_record_id, source_name, source_address, address_key, matched_by, er_version, match_status, first_seen_at, last_seen_at)
VALUES ('04a1e31e-4791-5216-ae15-73811d7b60ca', 3, 'websearch-2026-10-31:汕頭天天沙茶火鍋', '汕頭天天沙茶火鍋', '高雄市鹽埕區七賢三路240號', '七賢三路|240|', 'same_address+name', 'v0-manual-check', 'auto', '2026-10-31', '2026-10-31');
INSERT INTO identity.restaurant_source_entity (restaurant_id, source_id, source_record_id, source_name, source_address, address_key, industry_code, matched_by, er_version, match_status, first_seen_at, last_seen_at)
VALUES (NULL, 1, '62168762|高雄市鹽埕區七賢三路２４４之１號１樓', '天天沙茶火鍋有限公司', '高雄市鹽埕區七賢三路２４４之１號１樓', '七賢三路|244|1', '561115', 'name_only', 'v0-manual-check', 'review', '2026-10-31', '2026-10-31');
INSERT INTO identity.er_review_queue (source_entity_id, candidate_restaurant_id, reason, features)
SELECT source_entity_id, '04a1e31e-4791-5216-ae15-73811d7b60ca', 'chain_branch', '{"note": "newer company registration of the same brand at a different address"}'::jsonb
FROM identity.restaurant_source_entity WHERE source_id = 1 AND source_record_id LIKE '62168762|%';
INSERT INTO enrichment.restaurant_cuisine VALUES ('04a1e31e-4791-5216-ae15-73811d7b60ca', '火鍋', 'derived', 'MEDIUM', '2026-10-31');
COMMIT;
