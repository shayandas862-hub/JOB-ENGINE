-- 0019 · Phase 2 Task 3 — seed soc_going_rates for the queue-relevant tech codes.
--
-- Source: gov.uk Immigration Rules, Appendix Skilled Occupations, Table 1
-- (page version "Updated: 1 July 2026", fetched 2026-07-10). Deliberately a
-- PARTIAL seed: the 17 occupation codes this engine's listings can realistically
-- resolve to. Codes without a rate fall back to the profile's flat threshold in
-- the wall (advisory either way). 3544/3573 are absent from Table 1 (not
-- RQF6-eligible) — intentionally not seeded.
-- Applied via Supabase MCP 2026-07-10. Note: skilled_worker_occupations holds
-- NO rate data (the v1 assumption was wrong) — gov.uk is the source of truth.

begin;

create unique index if not exists soc_going_rates_code_unique
  on public.soc_going_rates (occupation_code);

insert into public.soc_going_rates
  (occupation_code, going_rate_annual, basis, effective_from, source)
values
  ('1137', 86000, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2131', 58200, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2132', 55000, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2133', 54900, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2134', 54700, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2135', 48500, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2136', 41200, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2137', 45600, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2139', 52300, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2141', 43800, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2161', 54400, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2422', 45800, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2431', 50200, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('2433', 55100, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('3131', 35200, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('3132', 33400, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10'),
  ('3133', 34600, 'annual, standard 37.5h week (Table 1)', '2026-07-01', 'gov.uk Appendix Skilled Occupations, fetched 2026-07-10')
on conflict (occupation_code) do update set
  going_rate_annual = excluded.going_rate_annual,
  basis             = excluded.basis,
  effective_from    = excluded.effective_from,
  source            = excluded.source;

commit;
