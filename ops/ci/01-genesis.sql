-- ops/ci/01-genesis.sql — GENERATED. Do not edit by hand.
--
-- The schema as it stood BEFORE migration 0001: the eight tables Phase 1
-- created through the Supabase dashboard, before db/migrations/ existed.
-- See B-GAE-024. Regenerate with ops/ci/generate-genesis.py; the result is
-- proven by ops/ci/apply-schema.sh, which applies this plus every migration to
-- a blank Postgres and diffs the outcome against the live schema.
--
-- Column types, defaults, generated expressions and identity clauses are
-- pg_dump's, verbatim. Columns, constraints and indexes that migrations add
-- are subtracted, parsed from the log itself.
-- Trigger functions first: the tables' triggers call them.

CREATE OR REPLACE FUNCTION public.set_skill_norm()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN
  NEW.skill_norm = lower(trim(NEW.skill_asked));
  NEW.updated_at = now();
  RETURN NEW;
END;
$function$;

CREATE OR REPLACE FUNCTION public.set_updated_at()
 RETURNS trigger
 LANGUAGE plpgsql
AS $function$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$function$;

CREATE TABLE public.cowork_findings (
    finding_id bigint NOT NULL,
    dedupe_key text NOT NULL,
    source text DEFAULT 'cowork'::text NOT NULL,
    trigger_id text,
    run_date date DEFAULT CURRENT_DATE NOT NULL,
    first_seen timestamp with time zone DEFAULT now() NOT NULL,
    last_seen timestamp with time zone DEFAULT now() NOT NULL,
    company_name text NOT NULL,
    company_norm text NOT NULL,
    matched_sponsor_id bigint,
    matched_sponsor_name text,
    sponsor_match_method text,
    sponsor_rating text,
    sponsor_is_skilled_worker boolean,
    sponsor_source text,
    matched_company_id bigint,
    role_title text NOT NULL,
    location text,
    salary_min integer,
    salary_max integer,
    salary_text text,
    role_url text NOT NULL,
    posted_at date,
    posted_evidence text,
    jd_full text,
    skills jsonb,
    soc_hint text,
    sponsorship_stance text,
    sponsorship_evidence text,
    filter_score integer,
    filter_verdict text,
    filter_notes text,
    status text DEFAULT 'provisional'::text NOT NULL,
    promoted_role_id text,
    notes text,
    CONSTRAINT cowork_findings_source_check CHECK ((source = 'cowork'::text)),
    CONSTRAINT cowork_findings_sponsorship_stance_check CHECK (((sponsorship_stance IS NULL) OR (sponsorship_stance = ANY (ARRAY['explicit_yes'::text, 'form_neutral'::text, 'register_only'::text, 'explicit_no'::text]))))
);

ALTER TABLE public.cowork_findings ALTER COLUMN finding_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.cowork_findings_finding_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE public.decisions (
    id bigint NOT NULL,
    decision_id text,
    title text,
    decision_summary text,
    situation_summary text,
    prediction text,
    outcome text,
    influenced_by text,
    decision_driver text,
    domain text[],
    entry_type text,
    goal_tags text[],
    state_flag text,
    state_score text,
    state_notes text,
    status text,
    related_decisions text,
    superseded_by text,
    supersedes text,
    session_date text,
    date_decided date,
    body_markdown text,
    notion_created_at timestamp with time zone,
    notion_url text,
    imported_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.decisions ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.decisions_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE public.licensed_sponsors (
    id bigint NOT NULL,
    organisation_name text NOT NULL,
    town_city text,
    county text,
    type_rating text NOT NULL,
    route text NOT NULL,
    org_name_norm text GENERATED ALWAYS AS (lower(regexp_replace(TRIM(BOTH FROM organisation_name), '\s+'::text, ' '::text, 'g'::text))) STORED,
    rating text GENERATED ALWAYS AS (
CASE
    WHEN ((type_rating ~~ '%(A %'::text) OR (type_rating ~~ '%(A)%'::text) OR (type_rating ~~ '%A rating%'::text)) THEN 'A'::text
    WHEN (type_rating ~~ '%B rating%'::text) THEN 'B'::text
    WHEN (type_rating ~~ '%Provisional%'::text) THEN 'Provisional'::text
    ELSE NULL::text
END) STORED,
    is_skilled_worker boolean GENERATED ALWAYS AS ((route = 'Skilled Worker'::text)) STORED,
    source_file text DEFAULT '2026-06-16_Worker_and_Temporary_Worker.csv'::text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.licensed_sponsors ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.licensed_sponsors_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE public.role_listings (
    role_id bigint NOT NULL,
    company_id bigint NOT NULL,
    role_title text NOT NULL,
    salary_text text,
    sponsors_this_role text,
    soc_code text,
    role_status text,
    date_opened date,
    deadline date,
    role_url text,
    jd_full text,
    application_status text DEFAULT 'not_applied'::text NOT NULL,
    applied_date date,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.role_listings ALTER COLUMN role_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.role_listings_role_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE public.role_skills (
    skill_id bigint NOT NULL,
    role_id bigint NOT NULL,
    skill_asked text NOT NULL,
    skill_norm text,
    skill_type text,
    evidence text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.role_skills ALTER COLUMN skill_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.role_skills_skill_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE public.skilled_worker_occupations (
    id bigint NOT NULL,
    occupation_code text NOT NULL,
    job_type text NOT NULL,
    related_job_titles text,
    eligibility_raw text NOT NULL,
    eligibility_tier text GENERATED ALWAYS AS (
CASE
    WHEN (eligibility_raw ~~* 'Higher Skilled%'::text) THEN 'Higher Skilled'::text
    WHEN (eligibility_raw ~~* 'Medium Skilled%'::text) THEN 'Medium Skilled'::text
    WHEN (eligibility_raw ~~* 'Ineligible%'::text) THEN 'Ineligible'::text
    ELSE 'Other'::text
END) STORED,
    is_higher_skilled boolean GENERATED ALWAYS AS ((eligibility_raw ~~* 'Higher Skilled%'::text)) STORED,
    has_conditions boolean GENERATED ALWAYS AS ((eligibility_raw <> ALL (ARRAY['Higher Skilled'::text, 'Medium Skilled'::text, 'Ineligible'::text]))) STORED,
    source_file text DEFAULT 'UK_Skilled_Worker_Occupations.xlsx'::text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.skilled_worker_occupations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.skilled_worker_occupations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE public.target_companies (
    company_id bigint NOT NULL,
    company_name text NOT NULL,
    sponsor_id bigint,
    lane text,
    city text,
    fit_rank text,
    sponsor_confidence text,
    web_checked boolean DEFAULT false NOT NULL,
    manually_verified boolean DEFAULT false NOT NULL,
    careers_url text,
    ats_type text,
    company_status text DEFAULT 'not_started'::text NOT NULL,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.target_companies ALTER COLUMN company_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.target_companies_company_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

CREATE TABLE public.target_roles (
    id bigint NOT NULL,
    search_title text NOT NULL,
    canonical_role text NOT NULL,
    priority_tier text,
    notes text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE public.target_roles ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.target_roles_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);

ALTER TABLE ONLY public.cowork_findings
    ADD CONSTRAINT cowork_findings_dedupe_key_key UNIQUE (dedupe_key);

ALTER TABLE ONLY public.cowork_findings
    ADD CONSTRAINT cowork_findings_pkey PRIMARY KEY (finding_id);

ALTER TABLE ONLY public.decisions
    ADD CONSTRAINT decisions_decision_id_key UNIQUE (decision_id);

ALTER TABLE ONLY public.decisions
    ADD CONSTRAINT decisions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.licensed_sponsors
    ADD CONSTRAINT licensed_sponsors_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.role_listings
    ADD CONSTRAINT role_listings_pkey PRIMARY KEY (role_id);

ALTER TABLE ONLY public.role_skills
    ADD CONSTRAINT role_skills_pkey PRIMARY KEY (skill_id);

ALTER TABLE ONLY public.skilled_worker_occupations
    ADD CONSTRAINT skilled_worker_occupations_occupation_code_key UNIQUE (occupation_code);

ALTER TABLE ONLY public.skilled_worker_occupations
    ADD CONSTRAINT skilled_worker_occupations_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.target_companies
    ADD CONSTRAINT target_companies_pkey PRIMARY KEY (company_id);

ALTER TABLE ONLY public.target_roles
    ADD CONSTRAINT target_roles_pkey PRIMARY KEY (id);

CREATE INDEX cowork_findings_company_norm_idx ON public.cowork_findings USING btree (company_norm);

CREATE INDEX cowork_findings_run_date_idx ON public.cowork_findings USING btree (run_date);

CREATE INDEX idx_decisions_decision_id ON public.decisions USING btree (decision_id);

CREATE INDEX idx_decisions_entry_type ON public.decisions USING btree (entry_type);

CREATE INDEX idx_decisions_status ON public.decisions USING btree (status);

CREATE INDEX idx_occ_higher ON public.skilled_worker_occupations USING btree (is_higher_skilled) WHERE is_higher_skilled;

CREATE INDEX idx_occ_tier ON public.skilled_worker_occupations USING btree (eligibility_tier);

CREATE INDEX idx_roles_company ON public.role_listings USING btree (company_id);

CREATE INDEX idx_skills_norm ON public.role_skills USING btree (skill_norm);

CREATE INDEX idx_skills_role ON public.role_skills USING btree (role_id);

CREATE INDEX idx_sponsors_org_norm ON public.licensed_sponsors USING btree (org_name_norm);

CREATE INDEX idx_sponsors_org_trgm ON public.licensed_sponsors USING gin (org_name_norm public.gin_trgm_ops);

CREATE INDEX idx_sponsors_route ON public.licensed_sponsors USING btree (route);

CREATE INDEX idx_sponsors_skilled ON public.licensed_sponsors USING btree (is_skilled_worker) WHERE is_skilled_worker;

CREATE INDEX idx_target_roles_canonical ON public.target_roles USING btree (canonical_role);

CREATE UNIQUE INDEX skilled_worker_occupations_code_unique ON public.skilled_worker_occupations USING btree (occupation_code);

CREATE TRIGGER trg_companies_updated BEFORE UPDATE ON public.target_companies FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_decisions_updated BEFORE UPDATE ON public.decisions FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_occ_updated BEFORE UPDATE ON public.skilled_worker_occupations FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_roles_updated BEFORE UPDATE ON public.role_listings FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_skill_norm BEFORE INSERT OR UPDATE ON public.role_skills FOR EACH ROW EXECUTE FUNCTION public.set_skill_norm();

CREATE TRIGGER trg_sponsors_updated BEFORE UPDATE ON public.licensed_sponsors FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_target_roles_updated BEFORE UPDATE ON public.target_roles FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

ALTER TABLE ONLY public.role_listings
    ADD CONSTRAINT role_listings_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.target_companies(company_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.role_skills
    ADD CONSTRAINT role_skills_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.role_listings(role_id) ON DELETE CASCADE;

ALTER TABLE ONLY public.target_companies
    ADD CONSTRAINT target_companies_sponsor_id_fkey FOREIGN KEY (sponsor_id) REFERENCES public.licensed_sponsors(id);

ALTER TABLE public.cowork_findings ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.decisions ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.licensed_sponsors ENABLE ROW LEVEL SECURITY;

CREATE POLICY occ_anon_read ON public.skilled_worker_occupations FOR SELECT TO anon USING (true);

CREATE POLICY occ_authenticated_all ON public.skilled_worker_occupations TO authenticated USING (true) WITH CHECK (true);

ALTER TABLE public.role_listings ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.role_skills ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.skilled_worker_occupations ENABLE ROW LEVEL SECURITY;

CREATE POLICY sponsors_anon_read ON public.licensed_sponsors FOR SELECT TO anon USING (true);

CREATE POLICY sponsors_authenticated_all ON public.licensed_sponsors TO authenticated USING (true) WITH CHECK (true);

ALTER TABLE public.target_companies ENABLE ROW LEVEL SECURITY;

ALTER TABLE public.target_roles ENABLE ROW LEVEL SECURITY;

ALTER TABLE ONLY public.target_roles
    ADD CONSTRAINT target_roles_search_title_key UNIQUE (search_title);

