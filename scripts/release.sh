#!/usr/bin/env bash

set -Eeuo pipefail
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_common.sh"

ENV_FILE=""
PREVIOUS_ENV_FILE=""
STATE_DIR=""
BACKUP_DIR=""
SMOKE_EMAIL=""
SMOKE_PASSWORD_FILE=""
COMPATIBILITY_EVIDENCE=""
RECOVER_STALE_LOCK=false
LOCK_DIR=""
LOCK_OWNED=false
EDGE_OPEN=false
PREVIOUS_PROBE_OPEN=false
PROBE_DIR=""

usage() {
  cat >&2 <<'EOF'
Usage: scripts/release.sh --env-file PATH --state-dir PATH --backup-dir PATH
       [--smoke-email ADDRESS --smoke-password-file PATH]
       --compatibility-evidence PATH [--previous-env-file PATH]
       [--recover-stale-lock]
EOF
}

cleanup() {
  local exit_code=$?
  set +e
  if (( exit_code != 0 )); then
    release_stop_edge_if_open "${EDGE_OPEN}" "${ENV_FILE}" || true
    if [[ "${PREVIOUS_PROBE_OPEN}" == true && -n "${PREVIOUS_ENV_FILE}" ]]; then
      docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${PREVIOUS_ENV_FILE}" \
        stop api >/dev/null 2>&1 || true
    fi
    release_log release failed >&2
  fi
  if [[ "${LOCK_OWNED}" == true && -n "${LOCK_DIR}" ]]; then
    rm -rf -- "${LOCK_DIR}"
  fi
  if [[ -n "${PROBE_DIR}" && -d "${PROBE_DIR}" ]]; then
    rm -rf -- "${PROBE_DIR}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT HUP INT TERM

while (( $# > 0 )); do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift ;;
    --previous-env-file) PREVIOUS_ENV_FILE="$2"; shift ;;
    --state-dir) STATE_DIR="$2"; shift ;;
    --backup-dir) BACKUP_DIR="$2"; shift ;;
    --smoke-email) SMOKE_EMAIL="$2"; shift ;;
    --smoke-password-file) SMOKE_PASSWORD_FILE="$2"; shift ;;
    --compatibility-evidence) COMPATIBILITY_EVIDENCE="$2"; shift ;;
    --recover-stale-lock) RECOVER_STALE_LOCK=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
  shift
done

[[ -r "${ENV_FILE}" && -n "${STATE_DIR}" && -n "${BACKUP_DIR}" \
  && -n "${COMPATIBILITY_EVIDENCE}" ]] || { usage; exit 2; }
release_require_commands docker jq mktemp python3 sha256sum
cd "${RELEASE_REPO_ROOT}"
release_require_path_outside_repository "${BACKUP_DIR}" "backup output"
release_require_path_outside_repository "${COMPATIBILITY_EVIDENCE}" \
  "compatibility receipt"

mkdir -p -- "${STATE_DIR}"
chmod 700 "${STATE_DIR}"
STATE_DIR="$(cd "${STATE_DIR}" && pwd)"
case "${STATE_DIR}/" in
  "${RELEASE_REPO_ROOT}/"*) echo "ERROR: release state must stay outside the repository" >&2; exit 2 ;;
esac
LOCK_DIR="${STATE_DIR}/.release.lock"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
  if [[ "${RECOVER_STALE_LOCK}" != true ]]; then
    echo "ERROR: another release owns the lock; use --recover-stale-lock only after incident review" >&2
    exit 1
  fi
  stale_reference="${STATE_DIR}/stale-lock-recovery.reference"
  [[ -r "${stale_reference}" ]] \
    || { echo "ERROR: stale lock recovery requires ${stale_reference}" >&2; exit 1; }
  stale_host="$(jq -r '.host // empty' "${LOCK_DIR}/owner.json" 2>/dev/null || true)"
  stale_pid="$(jq -r '.pid // empty' "${LOCK_DIR}/owner.json" 2>/dev/null || true)"
  if [[ "${stale_host}" == "$(hostname)" && "${stale_pid}" =~ ^[0-9]+$ ]] \
    && kill -0 "${stale_pid}" 2>/dev/null; then
    echo "ERROR: release lock owner is still running" >&2
    exit 1
  fi
  stale_digest="$(sha256sum "${stale_reference}" | awk '{print $1}')"
  mv -- "${LOCK_DIR}" "${STATE_DIR}/stale-lock-$(date -u +%Y%m%dT%H%M%SZ)-${stale_digest}"
  mkdir "${LOCK_DIR}"
fi
LOCK_OWNED=true
python3 - "${LOCK_DIR}/owner.json" "$(hostname)" "$$" <<'PY'
import json
import os
import sys
from datetime import UTC, datetime

path, host, pid = sys.argv[1:]
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    json.dump(
        {"host": host, "pid": int(pid), "started_at": datetime.now(UTC).isoformat()},
        output,
        sort_keys=True,
        separators=(",", ":"),
    )
    output.write("\n")
PY

preflight_args=(preflight --env-file "${ENV_FILE}" --compose-file "${RELEASE_COMPOSE_FILE}")
if [[ "${RELEASE_LOCAL_REHEARSAL:-false}" == true ]]; then
  preflight_args+=(--local-rehearsal)
fi
preflight="$(python3 scripts/release_contract.py "${preflight_args[@]}")"
release_id="$(jq -r '.release_id' <<<"${preflight}")"
revision="$(jq -r '.release_revision' <<<"${preflight}")"
export RELEASE_LOG_RELEASE_ID="${release_id}"
export RELEASE_LOG_REVISION="${revision}"
config_sha256="$(jq -r '.config_sha256' <<<"${preflight}")"
backend_image="$(release_env_value "${ENV_FILE}" BACKEND_IMAGE)"
frontend_image="$(release_env_value "${ENV_FILE}" FRONTEND_IMAGE)"
previous_release_id="$(release_env_value "${ENV_FILE}" PREVIOUS_RELEASE_ID 2>/dev/null || true)"
previous_revision=""
previous_backend_image=""
if [[ -n "${previous_release_id}" ]]; then
  [[ -r "${PREVIOUS_ENV_FILE}" ]] \
    || { echo "ERROR: predecessor releases require the previous environment" >&2; exit 2; }
  [[ "$(release_env_value "${PREVIOUS_ENV_FILE}" RELEASE_ID)" == "${previous_release_id}" ]] \
    || { echo "ERROR: previous environment does not match PREVIOUS_RELEASE_ID" >&2; exit 1; }
  previous_revision="$(release_env_value "${PREVIOUS_ENV_FILE}" RELEASE_REVISION)"
  previous_backend_image="$(release_env_value "${PREVIOUS_ENV_FILE}" BACKEND_IMAGE)"
  [[ -n "${SMOKE_EMAIL}" && -r "${SMOKE_PASSWORD_FILE}" ]] \
    || { echo "ERROR: predecessor releases require smoke account credentials" >&2; exit 2; }
  python3 - "${SMOKE_PASSWORD_FILE}" "${RELEASE_REPO_ROOT}" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser().resolve()
repository = Path(sys.argv[2]).resolve()
if not path.is_file() or not os.access(path, os.R_OK):
    raise SystemExit("ERROR: smoke password file is not a readable regular file")
if path == repository or repository in path.parents:
    raise SystemExit("ERROR: smoke password file must stay outside the repository")
if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
    raise SystemExit("ERROR: smoke password file must have mode 0600 or stricter")
PY
elif [[ -n "${SMOKE_EMAIL}" || -n "${SMOKE_PASSWORD_FILE}" \
  || -n "${PREVIOUS_ENV_FILE}" ]]; then
  echo "ERROR: first-release smoke must not invent predecessor authority" >&2
  exit 2
fi
state_file="${STATE_DIR}/${release_id}.json"
compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${ENV_FILE}")
if [[ "${RELEASE_LOCAL_REHEARSAL:-false}" != true ]]; then
  "${compose[@]}" pull --policy always >/dev/null
fi
python3 scripts/release_contract.py "${preflight_args[@]}" --check-images >/dev/null
if [[ -n "${previous_release_id}" ]]; then
  previous_preflight_args=(preflight --env-file "${PREVIOUS_ENV_FILE}" \
    --compose-file "${RELEASE_COMPOSE_FILE}" --expected-checkout-revision "${revision}")
  if [[ "${RELEASE_LOCAL_REHEARSAL:-false}" == true ]]; then
    previous_preflight_args+=(--local-rehearsal)
  else
    docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${PREVIOUS_ENV_FILE}" \
      pull --policy always >/dev/null
  fi
  python3 scripts/release_contract.py "${previous_preflight_args[@]}" --check-images >/dev/null
fi
python3 scripts/release_contract.py state-init \
  --state-file "${state_file}" --release-id "${release_id}" --revision "${revision}" \
  --backend-image "${backend_image}" --frontend-image "${frontend_image}" \
  --config-sha256 "${config_sha256}" --previous-release-id "${previous_release_id}" >/dev/null
python3 scripts/release_contract.py state-advance \
  --state-file "${state_file}" --release-id "${release_id}" --stage preflight >/dev/null

bundle="${BACKUP_DIR}/${release_id}.tar.gpg"
passphrase_file="$(release_env_value "${ENV_FILE}" BACKUP_PASSPHRASE_FILE)"
if release_stage_done "${state_file}" backup; then
  backup_outcome="$(release_stage_outcome "${state_file}" backup)"
  if [[ "${backup_outcome}" == "bootstrap:no-predecessor-empty-database" ]]; then
    [[ -z "${previous_release_id}" ]] \
      || { echo "ERROR: bootstrap backup state conflicts with a predecessor" >&2; exit 1; }
  else
    scripts/verify_restore.sh --env-file "${ENV_FILE}" --bundle "${bundle}" \
      --passphrase-file "${passphrase_file}"
    complete_bundle_sha="$(jq -r '.bundle_sha256' "${bundle}.complete.json")"
    complete_manifest_sha="$(jq -r '.manifest_sha256' "${bundle}.complete.json")"
    [[ "${backup_outcome}" == "passed:${complete_bundle_sha}:${complete_manifest_sha}" ]] \
      || { echo "ERROR: retry backup authority conflicts with release state" >&2; exit 1; }
  fi
elif [[ -z "${previous_release_id}" ]]; then
  "${compose[@]}" up -d --wait --wait-timeout 120 db redis >/dev/null
  non_bootstrap_tables="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename <> 'spatial_ref_sys'")"
  [[ "${non_bootstrap_tables}" == "0" ]] \
    || { echo "ERROR: first release requires an empty database with no predecessor" >&2; exit 1; }
  python3 scripts/release_contract.py state-advance \
    --state-file "${state_file}" --release-id "${release_id}" --stage backup \
    --outcome "bootstrap:no-predecessor-empty-database" >/dev/null
else
  scripts/backup_release.sh --env-file "${ENV_FILE}" --state-file "${state_file}" \
    --output-dir "${BACKUP_DIR}" --leave-writers-stopped
  scripts/verify_restore.sh --env-file "${ENV_FILE}" --bundle "${bundle}" \
    --passphrase-file "${passphrase_file}"
  complete_bundle_sha="$(jq -r '.bundle_sha256' "${bundle}.complete.json")"
  complete_manifest_sha="$(jq -r '.manifest_sha256' "${bundle}.complete.json")"
  python3 scripts/release_contract.py state-advance \
    --state-file "${state_file}" --release-id "${release_id}" --stage backup \
    --outcome "passed:${complete_bundle_sha}:${complete_manifest_sha}" >/dev/null
fi

"${compose[@]}" stop edge >/dev/null 2>&1 || true
if ! release_stage_done "${state_file}" migration; then
  release_log migration starting
  if ! "${compose[@]}" --profile release run --rm -T --no-deps migrate; then
    heads="$("${compose[@]}" run --rm -T --no-deps api alembic heads | awk 'NF {print $1}')"
    current="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc 'SELECT version_num FROM alembic_version')"
    if [[ -z "${heads}" || "${current}" != "${heads}" ]]; then
      echo "ERROR: migration failed before reaching the exact image head; traffic remains stopped" >&2
      exit 1
    fi
    migration_response_lost="reconciled"
    release_log migration_response_lost "${migration_response_lost}"
  fi
  python3 scripts/release_contract.py state-advance \
    --state-file "${state_file}" --release-id "${release_id}" --stage migration >/dev/null
fi

forward_alembic_revision="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
  'SELECT version_num FROM alembic_version')"
if [[ ! -e "${COMPATIBILITY_EVIDENCE}" ]]; then
  generation_args=(compatibility-generate --output "${COMPATIBILITY_EVIDENCE}" \
    --env-file "${ENV_FILE}" --target-release-id "${release_id}" \
    --target-revision "${revision}" --target-backend-image "${backend_image}" \
    --previous-release-id "${previous_release_id}" --previous-revision "${previous_revision}" \
    --previous-backend-image "${previous_backend_image}" \
    --forward-alembic-revision "${forward_alembic_revision}")
  if [[ -n "${previous_release_id}" ]]; then
    PROBE_DIR="$(mktemp -d "${STATE_DIR}/.${release_id}.compatibility-probes.XXXXXX")"
    chmod 700 "${PROBE_DIR}"
    readiness_output="${PROBE_DIR}/readiness.json"
    report_schema_output="${PROBE_DIR}/report-schema.json"
    previous_compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" \
      --env-file "${PREVIOUS_ENV_FILE}")
    PREVIOUS_PROBE_OPEN=true
    "${previous_compose[@]}" up -d --no-build --wait --wait-timeout 120 \
      db redis api \
      >/dev/null
    "${previous_compose[@]}" exec -T api python - >"${readiness_output}" <<'PY'
import asyncio
import json
import os
from datetime import UTC, datetime
from urllib.request import urlopen

from sqlalchemy import text

from app.db.session import get_engine


async def main() -> None:
    with urlopen("http://127.0.0.1:8000/api/v1/health/ready", timeout=5) as response:
        if response.status != 200:
            raise RuntimeError("previous-image readiness endpoint failed")
    engine = get_engine()
    try:
        async with engine.connect() as connection:
            row = (
                await connection.execute(
                    text(
                        "SELECT (SELECT version_num FROM alembic_version), "
                        "(SELECT extversion FROM pg_extension WHERE extname='postgis')"
                    )
                )
            ).one()
    finally:
        await engine.dispose()
    print(
        json.dumps(
            {
                "event": "release_readiness",
                "status": "ready",
                "release_revision": os.environ["RELEASE_REVISION"],
                "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "checks": {
                    "api": {"status": "ok"},
                    "database": {
                        "alembic_revision": row[0],
                        "postgis_version": row[1],
                    },
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


asyncio.run(main())
PY
    report_canary=("${previous_compose[@]}" run --rm -T --no-deps)
    if [[ "${RELEASE_COMPATIBILITY_BREAK_REPORT_CANARY:-false}" == true ]]; then
      [[ "${RELEASE_LOCAL_REHEARSAL:-false}" == true ]] || {
        echo "ERROR: report-canary mutation is restricted to local rehearsal" >&2
        exit 2
      }
      report_canary+=(-e R55_BREAK_REPORT_CANARY=true)
    fi
    report_canary+=(api python -)
    "${report_canary[@]}" >"${report_schema_output}" <<'PY'
import asyncio
import json
import os
from datetime import UTC, datetime

from sqlalchemy import select, text

from app.db.session import get_engine
from app.models.report_issuance import ReportArtifact, ReportIssuance


async def main() -> None:
    engine = get_engine()
    try:
        async with engine.connect() as connection:
            if os.environ.get("R55_BREAK_REPORT_CANARY") == "true":
                await connection.execute(
                    text("SELECT r55_missing_previous_image_column FROM report_issuances")
                )
            await connection.execute(select(ReportIssuance).limit(1))
            await connection.execute(select(ReportArtifact).limit(1))
            forward_revision = (
                await connection.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one()
    finally:
        await engine.dispose()
    print(
        json.dumps(
            {
                "event": "report_schema_canary",
                "status": "passed",
                "release_revision": os.environ["RELEASE_REVISION"],
                "forward_alembic_revision": forward_revision,
                "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "checks": {
                    "report_issuances_select": "ok",
                    "report_artifacts_select": "ok",
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


asyncio.run(main())
PY
    chmod 600 "${readiness_output}" "${report_schema_output}"
    "${previous_compose[@]}" stop api >/dev/null
    PREVIOUS_PROBE_OPEN=false
    generation_args+=(--readiness-output "${readiness_output}" \
      --report-schema-output "${report_schema_output}")
  fi
  python3 scripts/release_contract.py "${generation_args[@]}" >/dev/null
  if [[ -n "${PROBE_DIR}" ]]; then
    rm -rf -- "${PROBE_DIR}"
    PROBE_DIR=""
  fi
fi

validation_args=(compatibility-validate --evidence "${COMPATIBILITY_EVIDENCE}" \
  --env-file "${ENV_FILE}" --target-release-id "${release_id}" \
  --target-revision "${revision}" --target-backend-image "${backend_image}" \
  --previous-release-id "${previous_release_id}" --previous-revision "${previous_revision}" \
  --previous-backend-image "${previous_backend_image}" \
  --forward-alembic-revision "${forward_alembic_revision}")
if release_stage_done "${state_file}" compatibility; then
  accepted_outcome="$(release_stage_outcome "${state_file}" compatibility)"
  [[ "${accepted_outcome}" == passed:* ]] \
    || { echo "ERROR: compatibility state lacks an accepted receipt" >&2; exit 1; }
  accepted_authority="${accepted_outcome#passed:}"
  validation_args+=(--accepted-receipt-sha256 "${accepted_authority%%:*}" \
    --accepted-receipt-hmac "${accepted_authority#*:}")
fi
evidence_authority="$(python3 scripts/release_contract.py "${validation_args[@]}")"

if ! release_stage_done "${state_file}" compatibility; then
  python3 scripts/release_contract.py state-advance \
    --state-file "${state_file}" --release-id "${release_id}" --stage compatibility \
    --outcome "passed:${evidence_authority}" >/dev/null
else
  [[ "$(release_stage_outcome "${state_file}" compatibility)" == "passed:${evidence_authority}" ]] \
    || { echo "ERROR: retry compatibility receipt conflicts with release state" >&2; exit 1; }
fi

"${compose[@]}" up -d --no-build --wait --wait-timeout 120 db redis api worker frontend >/dev/null
"${compose[@]}" exec -T api python -m app.operations.readiness --write-canary
"${compose[@]}" exec -T api python -c \
  'from app.models.report_issuance import ReportIssuance; print("{\"event\":\"report_schema_canary\",\"status\":\"ok\"}")' \
  >/dev/null

EDGE_OPEN=true
"${compose[@]}" up -d --no-build --wait --wait-timeout 120 edge >/dev/null
smoke_args=()
if [[ -z "${previous_release_id}" ]]; then
  smoke_args+=(--expect-empty-user-table)
else
  smoke_args+=(--email "${SMOKE_EMAIL}" --password-file "${SMOKE_PASSWORD_FILE}")
fi
COMPOSE_PRODUCTION_FILE="${RELEASE_COMPOSE_FILE}" COMPOSE_ENV_FILE="${ENV_FILE}" \
  SMOKE_BASE_URL="$(release_env_value "${ENV_FILE}" PUBLIC_ORIGIN)" \
  scripts/release_smoke.sh "${smoke_args[@]}"
python3 scripts/release_contract.py state-advance \
  --state-file "${state_file}" --release-id "${release_id}" --stage traffic >/dev/null
EDGE_OPEN=false
release_log release passed
trap - EXIT HUP INT TERM
rm -rf -- "${LOCK_DIR}"
LOCK_DIR=""
LOCK_OWNED=false
