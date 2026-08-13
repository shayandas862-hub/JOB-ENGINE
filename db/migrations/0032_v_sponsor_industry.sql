-- 0032_v_sponsor_industry.sql
-- Readable industry view: joins sponsor_census.industry_codes (numeric SIC)
-- to the sic_codes reference table (0031) so each matched sponsor shows its
-- industry in plain English. Read-only; no personal data (register orgs only).
-- Legacy 4-digit (pre-2007) codes have no SIC-2007 description and are omitted
-- from industry_descriptions (the raw codes remain in industry_codes).

create or replace view v_sponsor_industry as
select
    sc.org_name_norm,
    sc.organisation_name,
    sc.town_city,
    sc.registry_status,
    sc.industry_codes,
    coalesce(
        array_agg(sic.description order by u.ord)
            filter (where sic.description is not null),
        '{}'
    ) as industry_descriptions
from sponsor_census sc
left join lateral unnest(sc.industry_codes) with ordinality as u(code, ord) on true
left join sic_codes sic on sic.code = u.code
where sc.registry_outcome = 'matched'
group by sc.org_name_norm, sc.organisation_name, sc.town_city,
         sc.registry_status, sc.industry_codes;
