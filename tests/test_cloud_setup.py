"""Phase 8 task 2 — the cloud contract (ops/cloud/).

The daily pipeline becomes a Cloud Run Job on a morning-UK Cloud Scheduler
cron, secrets live in Google Secret Manager. These tests pin the setup
scripts' shape offline: one source of names, the exact seven-secret allowlist
(GEMINI and NOTION deliberately absent — retired/deferred by founder word;
MCP_TOKEN added in task 3 for the hosted door), values piped to gcloud stdin
so no secret ever echoes into a shell log.
The cloud resources themselves are proven live, with the founder watching.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.conftest import private_only

ROOT = Path(__file__).resolve().parents[1]
CLOUD = ROOT / "ops" / "cloud"
ENV_SH = CLOUD / "env.sh"
SETUP_SH = CLOUD / "setup.sh"
SECRETS_SH = CLOUD / "push-secrets.sh"
BUILD_SH = CLOUD / "build-push.sh"

WIF_SH = CLOUD / "setup-wif.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

SCRIPTS = (ENV_SH, SETUP_SH, SECRETS_SH, BUILD_SH, WIF_SH)

# These pin the shape of the DEPLOYMENT SCRIPTS in the repo, not the runtime.
# ops/ is deliberately kept out of the image (the Dockerfile's named COPY
# allowlist plus .dockerignore), so inside the container there is nothing here
# to assert about: the scripts that BUILT the artefact are not shipped BY it.
# Skip rather than fail — a permanently red suite inside the image trains
# everyone to ignore it, which is worse than the gap it reports.
pytestmark = pytest.mark.skipif(
    not CLOUD.is_dir(),
    reason="repo-only contract: ops/ is not in the container image by design")

# The allowlist, exactly (CLAUDE.md): ntfy lives DB-side, GEMINI is retired,
# NOTION is deferred, SUPABASE_*/thresholds are read by nothing.
# MCP_TOKEN joined in Phase 8 task 3 — the hosted MCP door refuses to serve
# without it (mcp_server/transport.py), so the cloud must carry it. Growing
# this list is a DELIBERATE contract change: add the name here and rename the
# count test with it, never loosen the assertion to make a failure go away.
EXPECTED_SECRETS = [
    "DATABASE_URL",
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
    "REED_API_KEY",
    "COMPANIES_HOUSE_API_KEY",
    "DASHBOARD_TOKEN",
    "MCP_TOKEN",
    # Task 6: the Supabase project URL the MCP door derives its JWKS endpoint
    # from. Not confidential — it is a public URL — but it carries the project
    # ref, which never enters the public repository, and Secret Manager is this
    # project's only path for a value that must stay out of git. Setting it is
    # what switches sign-in on.
    "SUPABASE_URL",
]


def _env_value(name: str) -> str:
    # env.sh pins every value in double quotes; trailing comments are fine.
    match = re.search(rf'^{name}="([^"]*)"', ENV_SH.read_text(), re.M)
    assert match, f"{name} not pinned in env.sh"
    return match.group(1)


def _section(title: str) -> str:
    """setup.sh's text under `echo "== <title> =="`, up to the next banner.

    setup.sh now deploys more than one surface, so a whole-file `in` check
    can no longer tell the daily Job's flags from the MCP service's — the
    job must NOT override the image's door, while the service must.
    """
    text = SETUP_SH.read_text()
    start = text.find(f'echo "== {title} ==')
    assert start != -1, f"no '== {title} ==' section in setup.sh"
    nxt = text.find('echo "== ', start + 1)
    return text[start:] if nxt == -1 else text[start:nxt]


def test_every_cloud_script_exists_and_fails_shut():
    for script in SCRIPTS:
        assert script.exists(), f"missing {script.name}"
        text = script.read_text()
        assert text.startswith("#!/usr/bin/env bash"), script.name
        assert "set -euo pipefail" in text, f"{script.name} must fail shut"


def test_one_source_of_names_pins_project_region_and_job():
    assert _env_value("PROJECT_ID") == "goal-a-engine"
    assert _env_value("REGION") == "europe-west2"          # London
    assert _env_value("JOB_NAME") == "goal-a-daily"
    for script in (SETUP_SH, SECRETS_SH, BUILD_SH):
        assert "env.sh" in script.read_text(), \
            f"{script.name} must source env.sh, never redefine names"


def test_the_morning_cron_runs_before_the_apply_hour_uk_time():
    # The founder applies from the queue every morning; the cloud fills it
    # at 06:30 Europe/London so the queue is fresh before he sits down.
    assert _env_value("SCHEDULE") == "30 6 * * *"
    assert _env_value("SCHEDULE_TZ") == "Europe/London"
    setup = SETUP_SH.read_text()
    assert '--schedule="${SCHEDULE}"' in setup
    assert '--time-zone="${SCHEDULE_TZ}"' in setup


def test_the_secret_allowlist_is_exactly_the_eight():
    # Eight since task 6 added SUPABASE_URL. The name carries the count on
    # purpose: a silent ninth secret is exactly what this test exists to stop.
    assert _env_value("SECRETS") == " ".join(EXPECTED_SECRETS)
    assert len(EXPECTED_SECRETS) == 8


def test_retired_and_deferred_keys_never_reach_the_cloud():
    # Gemini is retired (2026-08-03) and Notion is deferred by founder choice;
    # neither name may appear anywhere in the cloud setup.
    #
    # This used to ban the whole "SUPABASE_" prefix, because every such name in
    # the local .env was tooling the cloud had no use for. Task 6 makes exactly
    # one of them the cloud's business — SUPABASE_URL, the issuer the MCP door
    # verifies sign-in tokens against — so the ban is now by NAME. The three
    # still banned are the data API's credentials: the API this project does
    # not use (B-GAE-032, migration 0061), and a key for it in the cloud would
    # be a door reopened by config.
    for script in SCRIPTS:
        text = script.read_text()
        for banned in ("GEMINI", "NOTION", "SUPABASE_PUBLISHABLE",
                       "SUPABASE_SECRET", "SUPABASE_ANON"):
            assert banned not in text, f"{banned} in {script.name}"


def test_secret_values_flow_via_stdin_never_echo():
    text = SECRETS_SH.read_text()
    assert "--data-file=-" in text          # value arrives on stdin
    assert 'printf' in text                 # printf '%s' "$value" | gcloud …
    assert "set -x" not in text             # tracing would print values
    assert ".env" in text                   # source of truth stays local


def test_the_job_mounts_the_six_engine_secrets_and_only_runs_the_run_door():
    # Every secret mounts as an env var of the same name, version pinned live.
    assert _env_value("JOB_SECRETS").split() == EXPECTED_SECRETS[:6]
    job = _section("the daily job")
    assert "${JOB_SECRETS}" in job
    # The image's default door IS `run`: the job must not override the
    # entrypoint or args, so the contract stays with the Dockerfile.
    assert "--command" not in job
    assert "--args" not in job


def test_the_daily_job_never_receives_the_mcp_token():
    # Least privilege across surfaces. The job runs the pipeline and never
    # serves MCP, so handing it the door key would mean one compromised
    # surface leaks the other's credential for no working benefit.
    assert "MCP_TOKEN" not in _env_value("JOB_SECRETS")


def test_the_mcp_service_mounts_only_the_database_its_token_and_its_issuer():
    # It answers requests against the DB and guards the door — nothing else.
    # No aggregator keys: the tools that spawn scripts are not durable in a
    # Cloud Run service, so those keys would be exposure without benefit.
    # SUPABASE_URL joined in task 6 and is here alone: the MCP door is the only
    # surface that verifies a signed-in identity.
    assert _env_value("MCP_SECRETS").split() == ["DATABASE_URL", "MCP_TOKEN",
                                                 "SUPABASE_URL"]
    for banned in ("ADZUNA", "REED", "COMPANIES_HOUSE", "DASHBOARD_TOKEN"):
        assert banned not in _env_value("MCP_SECRETS")


def test_the_mcp_service_is_token_gated_scale_to_zero_and_own_identity():
    # Task 3. The token is the door (mcp_server/transport.py refuses to serve
    # without it), so the service itself is deployed --allow-unauthenticated:
    # Google IAM would block the founder's own AI client, which cannot mint
    # an OAuth token. That is why MCP_TOKEN is non-negotiable, not optional.
    mcp = _section("the hosted MCP service")
    assert '"${MCP_SERVICE}"' in mcp
    assert "${MCP_SECRETS}" in mcp                    # least privilege
    assert '--service-account "${MCP_EMAIL}"' in mcp  # not the job's identity
    assert "--min-instances 0" in mcp                 # costs nothing idle
    assert "MCP_TRANSPORT=http" in mcp                # the hosted door, not stdio


def test_the_mcp_service_runs_the_mcp_door_not_the_pipeline():
    # A door mix-up here would run the 12-minute pipeline inside a request.
    mcp = _section("the hosted MCP service")
    assert "--args mcp" in mcp
    assert "--args run" not in mcp


def test_the_public_status_service_carries_no_token_and_its_own_identity():
    # Task 4. This is the ONLY surface with no auth, so the thing that keeps it
    # safe is what it can reach: the 0043 views, through an identity that can
    # read one secret. It must never be handed a token it has no use for.
    assert _env_value("STATUS_SECRETS").split() == ["DATABASE_URL"]
    for banned in ("MCP_TOKEN", "DASHBOARD_TOKEN", "ADZUNA", "REED",
                   "COMPANIES_HOUSE"):
        assert banned not in _env_value("STATUS_SECRETS")
    status = _section("the public status page")
    assert '"${STATUS_SERVICE}"' in status
    assert '--service-account "${STATUS_EMAIL}"' in status   # not the MCP's
    assert "--args status" in status                         # the status door
    assert "--min-instances 0" in status


def test_the_status_page_is_the_only_surface_deployed_unauthenticated_on_purpose():
    # Both services pass --allow-unauthenticated, but for OPPOSITE reasons, and
    # confusing them would be the expensive mistake: the MCP is guarded by its
    # bearer token in code, while the status page genuinely has no secret to
    # protect. Each section must say which it is.
    assert "--allow-unauthenticated" in _section("the public status page")
    assert "--allow-unauthenticated" in _section("the hosted MCP service")
    assert "MCP_TOKEN" not in _section("the public status page")


def test_the_job_gets_room_to_finish_and_one_retry():
    setup = SETUP_SH.read_text()
    assert '--task-timeout="${JOB_TIMEOUT}"' in setup
    assert int(_env_value("JOB_TIMEOUT")) >= 3600     # register+classify nights
    assert '--max-retries=1' in setup                 # stages tolerate a rerun


def test_the_scheduler_fires_the_job_as_a_service_account_not_a_key():
    setup = SETUP_SH.read_text()
    assert ":run" in setup                            # Cloud Run Jobs run API
    assert "--oauth-service-account-email" in setup   # no exported keys, ever
    assert "roles/run.invoker" in setup
    assert "roles/secretmanager.secretAccessor" in setup


# ------------------------------------------------- task 5b: deploy on green
#
# The four tests below read `.github/workflows/ci.yml` for its DEPLOY jobs, and
# the public snapshot replaces that file with the two credential-free lanes
# (B-GAE-035). So they are a private-repo contract and say so: without the
# mark they fail inside the snapshot — which is to say the public repo's very
# first Actions run would have gone red again, for a brand new reason, in the
# same push that was meant to fix the red. Found by running the suite inside a
# trial snapshot before shipping, not by reading the diff.
#
# `test_no_service_account_key_is_ever_exported_anywhere` deliberately keeps
# running in both: it asserts an ABSENCE, which stays true and worth checking
# whichever workflow the file holds.


def test_no_service_account_key_is_ever_exported_anywhere():
    # ops/cloud/NOTES.md: "No service-account keys are ever exported." This is
    # the whole reason deploy-on-green waited for Workload Identity Federation
    # instead of taking the five-minute shortcut. A leaked JSON key is a
    # permanent credential; a WIF token lives for minutes and is bound to one
    # repository.
    for path in (*SCRIPTS, WORKFLOW):
        text = path.read_text()
        for banned in ("keys create", "credentials_json", "service_account_key",
                       "GCP_SA_KEY", "private_key"):
            assert banned not in text, f"{banned} in {path.name}"


@private_only
def test_the_deploy_job_authenticates_by_oidc_bound_to_this_repo():
    wf = WORKFLOW.read_text()
    assert "google-github-actions/auth@v2" in wf
    assert "workload_identity_provider:" in wf
    assert "id-token: write" in wf          # the OIDC token GitHub mints
    # WIF is only as good as its condition: without a repository restriction
    # any GitHub repo in the world could mint a token for this project.
    assert "attribute.repository" in WIF_SH.read_text()
    assert _env_value("GITHUB_REPO") == "shayandas862-hub/GOAL-A"


def test_the_deployer_identity_can_deploy_and_nothing_else():
    # Least privilege again: push an image, roll a revision, act as the runtime
    # identities. Not project owner, and no access to any secret VALUE.
    wif = WIF_SH.read_text()
    for role in ("roles/run.developer", "roles/artifactregistry.writer",
                 "roles/iam.serviceAccountUser"):
        assert role in wif, f"deployer missing {role}"
    for role in ("roles/owner", "roles/editor",
                 "roles/secretmanager.secretAccessor"):
        assert role not in wif, f"deployer must NOT hold {role}"


@private_only
def test_deploy_only_happens_on_green_main_never_on_a_pull_request():
    # A PR from a fork must never reach production. Both guards are required:
    # needs: makes it wait for the suite, if: pins it to a push on main.
    wf = WORKFLOW.read_text()
    deploy = wf[wf.index("  deploy:"):]
    assert "needs:" in deploy and "test" in deploy.split("needs:")[1][:80]
    assert "github.ref == 'refs/heads/main'" in deploy
    assert "github.event_name == 'push'" in deploy


@private_only
def test_a_doc_only_push_never_rebuilds_or_redeploys():
    # Cost and correctness at once. Rebuilding a ~380MB image and rolling three
    # cloud surfaces because a log entry was written burns CI minutes for
    # nothing — and it swaps the artefact out from under the rule that the
    # 06:30 image must be hand-run first. Tests still run on doc pushes,
    # because the suite reads the README and the git index.
    wf = WORKFLOW.read_text()
    assert "  changes:" in wf
    image = wf[wf.index("  image:"):wf.index("  deploy:")]
    assert "needs: [test, changes]" in image
    assert "needs.changes.outputs.code == 'true'" in image
    # The test job must NOT be gated — documents can break it.
    test_job = wf[wf.index("  test:"):wf.index("  image:")]
    assert "needs.changes" not in test_job


@private_only
def test_a_deploy_is_never_cancelled_midway():
    # The workflow-level concurrency cancels superseded runs, which is right for
    # tests and wrong for a job that updates three surfaces in sequence: a
    # cancellation between them leaves production on mixed images. Observed
    # live before this guard existed.
    wf = WORKFLOW.read_text()
    deploy = wf[wf.index("  deploy:"):]
    assert "concurrency:" in deploy
    assert "cancel-in-progress: false" in deploy


def test_build_pushes_an_amd64_image_tagged_by_git_sha():
    text = BUILD_SH.read_text()
    assert "--platform linux/amd64" in text           # Cloud Run's arch
    assert "git rev-parse --short HEAD" in text       # immutable tag
    assert "-docker.pkg.dev" in text                  # Artifact Registry
