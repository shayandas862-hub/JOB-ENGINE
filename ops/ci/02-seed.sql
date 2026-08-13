-- ops/ci/02-seed.sql — the smallest fixture that lets the RLS tests MEAN
-- something on a freshly built database.
--
-- Why a seed is needed at all, and why it is exactly this shape:
--
-- The isolation tests are all written to the B-GAE-011 rule — every "the
-- stranger is refused" assertion is PAIRED with the same read succeeding for the
-- row's owner, because a one-sided isolation test cannot tell "refused" from
-- "nothing there". On an empty database the refusals pass and the paired
-- controls fail, which is the tests working correctly. So the lane must give
-- them rows to be refused.
--
-- Measured on the freshly built schema before writing this: the migrations
-- themselves already seed profiles (1, from 0018), target_roles (10, from
-- 0046), soc_going_rates (17, from 0019), sic_codes (731, from 0031) and
-- promotion_rules (1). This file fills only what is still empty and only what a
-- test actually reads:
--
--   * the nine WORLD tables test_world_data_stays_readable counts, seven of
--     which had no rows;
--   * one target_companies row for the existing profile, plus the
--     role_listings / role_skills / listing_events chain hanging off it — the
--     DERIVED tables whose policies walk to target_companies.
--
-- EVERY VALUE HERE IS INVENTED. This file ships in the public snapshot, so it
-- carries no real sponsor, no real advert and no personal data. The listing is
-- written to pass the v_apply_queue gate (open, UK location, a title matching
-- one of 0046's seeded target_roles) so the queue tests have a row to scope.
--
-- Nothing writes to a GENERATED column: licensed_sponsors derives its norm and
-- rating columns, and 0001's my_skills derives skill_norm. That rule is the
-- whole of B-GAE-013.
BEGIN;

-- ── world data: owned by nobody, readable by everybody ──────────────────────
-- type_rating must be a real register phrasing, because rating is GENERATED
-- from it by a LIKE over '%(A %' / '%(A)%' / '%A rating%'. A tidy-looking
-- 'A (Premium)' silently generates rating = NULL.
INSERT INTO public.licensed_sponsors (organisation_name, type_rating, route)
VALUES ('Fictional Widgets Ltd', 'Worker (A rating)', 'Skilled Worker'),
       ('Imaginary Systems PLC',  'Worker (A rating)', 'Skilled Worker');

INSERT INTO public.sponsor_census (org_name_norm)
VALUES ('fictional widgets'), ('imaginary systems');

INSERT INTO public.skilled_worker_occupations
       (occupation_code, job_type, eligibility_raw)
VALUES ('2133', 'IT and telecommunications professionals', 'Eligible');

INSERT INTO public.aggregator_ads
       (source, external_id, employer_name, employer_norm, title,
        dedupe_key, content_fingerprint)
-- `source` is constrained to adzuna|reed, so the fixture cannot label itself
-- ci-fixture here; the invented external_id is what marks it.
VALUES ('adzuna', 'ci-fixture-0001', 'Fictional Widgets Ltd', 'fictional widgets',
        'AI Engineer', 'ci-fixture-dedupe-0001', 'ci-fixture-fingerprint-0001');

INSERT INTO public.skill_synonyms (raw_norm, canonical_label, canonical_norm)
VALUES ('py', 'Python', 'python');

INSERT INTO public.review_items (kind, summary)
VALUES ('skill_synonym', 'CI fixture: an ambiguity about a public fact');

INSERT INTO public.pipeline_runs (started_at, status)
VALUES (now(), 'ok');

-- ── one owner's private chain, hung off the profile the migrations created ───
-- The owner is READ, never hardcoded: a literal uuid would be personal data in
-- a public file, and it would rot the moment the row changed.
INSERT INTO public.target_companies (company_name, owner_id, fit_rank, lane)
SELECT 'Fictional Widgets Ltd', p.profile_id, 1, 'sponsor'
FROM public.profiles p ORDER BY p.created_at LIMIT 1;

-- THREE listings, not one, and titled deliberately:
--   * test_two_real_owners... asserts owner A holds more than one listing, so
--     that "A sees none of B's" is not a statement about a one-row table;
--   * every title must match one of 0046's seeded target_roles ('ML Engineer',
--     'Applied AI', 'Solution Architect') or v_apply_queue's data-driven gate
--     excludes it and the queue tests read nothing. A plain 'AI Engineer'
--     matches none of them — the gate is a normalised substring over the
--     owner's OWN target_roles, which is the whole point of 0046.
--   * the location must satisfy the view's UK gate.
INSERT INTO public.role_listings
       (company_id, role_title, location, role_status, role_url, jd_full)
SELECT c.company_id, v.title, 'London, United Kingdom', 'open',
       'https://example.invalid/ci-fixture/' || v.slug,
       'A fictional job description used only by the CI database lane.'
FROM public.target_companies c
CROSS JOIN (VALUES ('ML Engineer', 'ml-engineer'),
                   ('Applied AI Engineer', 'applied-ai-engineer'),
                   ('Solution Architect', 'solution-architect')) AS v(title, slug)
WHERE c.company_name = 'Fictional Widgets Ltd';

INSERT INTO public.role_skills (role_id, skill_asked, skill_type)
SELECT r.role_id, 'Python', 'required'
FROM public.role_listings r WHERE r.role_title = 'ML Engineer';

-- event_type is constrained to appeared|changed|closed|reopened.
INSERT INTO public.listing_events (role_id, event_type)
SELECT r.role_id, 'appeared'
FROM public.role_listings r WHERE r.role_title = 'ML Engineer';

COMMIT;
