#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_common.sh"

ENV_FILE=""
STATE_DIR=""
BACKUP_DIR=""
SMOKE_EMAIL=""
SMOKE_PASSWORD_FILE=""
COMPATIBILITY_EVIDENCE=""
RECOVER_STALE_LOCK=false
LOCK_DIR=""

usage() {
  cat >&2 <<'EOF'
Usage: scripts/release.sh --env-file PATH --state-dir PATH --backup-dir PATH
       --smoke-email ADDRESS --smoke-password-file PATH
       --compatibility-evidence PATH [--recover-stale-lock]
EOF
}

cleanup() {
  local exit_code=$?
  set +e
  [[ -z "${LOCK_DIR}" ]] || rm -rf -- "${LOCK_DIR}"
  if (( exit_code != 0 )); then
    release_log release failed >&2
  fi
  exit "${exit_code}"
}
trap cleanup EXIT HUP INT TERM

while (( $# > 0 )); do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift ;;
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
  && -n "${SMOKE_EMAIL}" && -r "${SMOKE_PASSWORD_FILE}" \
  && -r "${COMPATIBILITY_EVIDENCE}" ]] || { usage; exit 2; }
release_require_commands docker jq python3 sha256sum
cd "${RELEASE_REPO_ROOT}"

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
config_sha256="$(jq -r '.config_sha256' <<<"${preflight}")"
backend_image="$(release_env_value "${ENV_FILE}" BACKEND_IMAGE)"
frontend_image="$(release_env_value "${ENV_FILE}" FRONTEND_IMAGE)"
previous_release_id="$(release_env_value "${ENV_FILE}" PREVIOUS_RELEASE_ID 2>/dev/null || true)"
state_file="${STATE_DIR}/${release_id}.json"
compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${ENV_FILE}")
"${compose[@]}" pull --policy always >/dev/null
python3 scripts/release_contract.py "${preflight_args[@]}" --check-images >/dev/null
python3 scripts/release_contract.py state-init \
  --state-file "${state_file}" --release-id "${release_id}" --revision "${revision}" \
  --backend-image "${backend_image}" --frontend-image "${frontend_image}" \
  --config-sha256 "${config_sha256}" --previous-release-id "${previous_release_id}" >/dev/null
python3 scripts/release_contract.py state-advance \
  --state-file "${state_file}" --release-id "${release_id}" --stage preflight >/dev/null

if ! release_stage_done "${state_file}" backup; then
  scripts/backup_release.sh --env-file "${ENV_FILE}" --state-file "${state_file}" \
    --output-dir "${BACKUP_DIR}"
  python3 scripts/release_contract.py state-advance \
    --state-file "${state_file}" --release-id "${release_id}" --stage backup >/dev/null
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

"${compose[@]}" up -d --no-build --wait --wait-timeout 120 db redis api worker frontend >/dev/null
if ! release_stage_done "${state_file}" compatibility; then
  forward_alembic_revision="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
    'SELECT version_num FROM alembic_version')"
  evidence_sha256="$(python3 scripts/release_contract.py compatibility-validate \
    --evidence "${COMPATIBILITY_EVIDENCE}" --target-release-id "${release_id}" \
    --target-revision "${revision}" --target-backend-image "${backend_image}" \
    --previous-release-id "${previous_release_id}" \
    --forward-alembic-revision "${forward_alembic_revision}")"
  "${compose[@]}" exec -T api python -m app.operations.readiness --write-canary
  "${compose[@]}" exec -T api python -c \
    'from app.models.report_issuance import ReportIssuance; print("{\"event\":\"report_schema_canary\",\"status\":\"ok\"}")' \
    >/dev/null
  python3 scripts/release_contract.py state-advance \
    --state-file "${state_file}" --release-id "${release_id}" --stage compatibility \
    --outcome "passed:${evidence_sha256}" >/dev/null
fi

"${compose[@]}" up -d --no-build edge >/dev/null
COMPOSE_PRODUCTION_FILE="${RELEASE_COMPOSE_FILE}" COMPOSE_ENV_FILE="${ENV_FILE}" \
  SMOKE_BASE_URL="$(release_env_value "${ENV_FILE}" PUBLIC_ORIGIN)" \
  scripts/release_smoke.sh --email "${SMOKE_EMAIL}" --password-file "${SMOKE_PASSWORD_FILE}"
python3 scripts/release_contract.py state-advance \
  --state-file "${state_file}" --release-id "${release_id}" --stage traffic >/dev/null
release_log release passed
trap - EXIT HUP INT TERM
rm -rf -- "${LOCK_DIR}"
LOCK_DIR=""
