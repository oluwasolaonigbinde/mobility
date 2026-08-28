#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_common.sh"

CURRENT_STATE=""
PREVIOUS_ENV_FILE=""
STATE_DIR=""
SMOKE_EMAIL=""
SMOKE_PASSWORD_FILE=""
COMPATIBILITY_EVIDENCE=""
LOCK_DIR=""

cleanup() {
  local exit_code=$?
  set +e
  [[ -z "${LOCK_DIR}" ]] || rm -rf -- "${LOCK_DIR}"
  if (( exit_code != 0 )); then
    release_log release_recovery failed >&2
  fi
  exit "${exit_code}"
}
trap cleanup EXIT HUP INT TERM

usage() {
  cat >&2 <<'EOF'
Usage: scripts/recover_release.sh --current-state PATH --previous-env-file PATH
       --state-dir PATH --smoke-email ADDRESS --smoke-password-file PATH
       --compatibility-evidence PATH
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --current-state) CURRENT_STATE="$2"; shift ;;
    --previous-env-file) PREVIOUS_ENV_FILE="$2"; shift ;;
    --state-dir) STATE_DIR="$2"; shift ;;
    --smoke-email) SMOKE_EMAIL="$2"; shift ;;
    --smoke-password-file) SMOKE_PASSWORD_FILE="$2"; shift ;;
    --compatibility-evidence) COMPATIBILITY_EVIDENCE="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
  shift
done

[[ -r "${CURRENT_STATE}" && -r "${PREVIOUS_ENV_FILE}" && -n "${STATE_DIR}" \
  && -n "${SMOKE_EMAIL}" && -r "${SMOKE_PASSWORD_FILE}" \
  && -r "${COMPATIBILITY_EVIDENCE}" ]] || { usage; exit 2; }
release_require_commands docker jq python3 sha256sum
cd "${RELEASE_REPO_ROOT}"

mkdir -p -- "${STATE_DIR}"
chmod 700 "${STATE_DIR}"
STATE_DIR="$(cd "${STATE_DIR}" && pwd)"
case "${STATE_DIR}/" in
  "${RELEASE_REPO_ROOT}/"*) echo "ERROR: recovery state must stay outside the repository" >&2; exit 2 ;;
esac
LOCK_DIR="${STATE_DIR}/.release.lock"
mkdir "${LOCK_DIR}" 2>/dev/null \
  || { echo "ERROR: another release or recovery owns the lock" >&2; exit 1; }
printf '{"host":"%s","pid":%s,"operation":"recovery"}\n' "$(hostname)" "$$" \
  >"${LOCK_DIR}/owner.json"
chmod 600 "${LOCK_DIR}/owner.json"

preflight_args=(preflight --env-file "${PREVIOUS_ENV_FILE}" \
  --compose-file "${RELEASE_COMPOSE_FILE}" \
  --expected-checkout-revision "$(jq -r '.revision' "${CURRENT_STATE}")")
python3 scripts/release_contract.py "${preflight_args[@]}" >/dev/null
previous_release_id="$(release_env_value "${PREVIOUS_ENV_FILE}" RELEASE_ID)"
[[ "$(jq -r '.previous_release_id' "${CURRENT_STATE}")" == "${previous_release_id}" ]] \
  || { echo "ERROR: previous environment does not match current release authority" >&2; exit 1; }
previous_revision="$(release_env_value "${PREVIOUS_ENV_FILE}" RELEASE_REVISION)"
previous_backend_image="$(release_env_value "${PREVIOUS_ENV_FILE}" BACKEND_IMAGE)"

compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${PREVIOUS_ENV_FILE}")
"${compose[@]}" pull --policy always >/dev/null
python3 scripts/release_contract.py "${preflight_args[@]}" --check-images >/dev/null
forward_alembic_revision="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
  'SELECT version_num FROM alembic_version')"
compatibility_sha256="$(python3 scripts/release_contract.py compatibility-validate \
  --evidence "${COMPATIBILITY_EVIDENCE}" \
  --target-release-id "$(jq -r '.release_id' "${CURRENT_STATE}")" \
  --target-revision "$(jq -r '.revision' "${CURRENT_STATE}")" \
  --target-backend-image "$(jq -r '.backend_image' "${CURRENT_STATE}")" \
  --previous-release-id "${previous_release_id}" \
  --forward-alembic-revision "${forward_alembic_revision}")"
[[ "$(jq -r '.previous_revision' "${COMPATIBILITY_EVIDENCE}")" == "${previous_revision}" \
  && "$(jq -r '.previous_backend_image' "${COMPATIBILITY_EVIDENCE}")" == "${previous_backend_image}" ]] \
  || { echo "ERROR: compatibility evidence does not bind the previous image" >&2; exit 1; }
"${compose[@]}" stop edge api worker frontend >/dev/null 2>&1 || true
"${compose[@]}" up -d --no-build --wait --wait-timeout 120 db redis api worker frontend >/dev/null
# Recovery never runs an Alembic downgrade. The supplied compatibility evidence
# must prove the previous image against the forward-migrated schema.
"${compose[@]}" exec -T api python -m app.operations.readiness \
  --write-canary --allow-database-ahead
"${compose[@]}" up -d --no-build edge >/dev/null
COMPOSE_PRODUCTION_FILE="${RELEASE_COMPOSE_FILE}" COMPOSE_ENV_FILE="${PREVIOUS_ENV_FILE}" \
  SMOKE_BASE_URL="$(release_env_value "${PREVIOUS_ENV_FILE}" PUBLIC_ORIGIN)" \
  scripts/release_smoke.sh --email "${SMOKE_EMAIL}" --password-file "${SMOKE_PASSWORD_FILE}"

python3 - "${STATE_DIR}/recovery-$(date -u +%Y%m%dT%H%M%SZ).json" \
  "$(jq -r '.release_id' "${CURRENT_STATE}")" "${previous_release_id}" "${compatibility_sha256}" <<'PY'
import json
import os
import sys
from datetime import UTC, datetime

path, failed_release, recovered_release, evidence_sha256 = sys.argv[1:]
payload = {
    "schema_version": 1,
    "event": "release_recovery",
    "failed_release_id": failed_release,
    "recovered_release_id": recovered_release,
    "compatibility_evidence_sha256": evidence_sha256,
    "database_downgrade": False,
    "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    json.dump(payload, output, sort_keys=True, separators=(",", ":"))
    output.write("\n")
PY
release_log release_recovery passed
trap - EXIT HUP INT TERM
rm -rf -- "${LOCK_DIR}"
LOCK_DIR=""
