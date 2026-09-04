#!/usr/bin/env bash

set -Eeuo pipefail
umask 077
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_common.sh"

CURRENT_STATE=""
CURRENT_ENV_FILE=""
PREVIOUS_ENV_FILE=""
STATE_DIR=""
SMOKE_EMAIL=""
SMOKE_PASSWORD_FILE=""
COMPATIBILITY_EVIDENCE=""
LOCK_DIR=""
LOCK_OWNED=false
EDGE_OPEN=false

cleanup() {
  local exit_code=$?
  set +e
  if (( exit_code != 0 )); then
    release_stop_edge_if_open "${EDGE_OPEN}" "${PREVIOUS_ENV_FILE}" || true
    release_log release_recovery failed >&2
  fi
  if [[ "${LOCK_OWNED}" == true && -n "${LOCK_DIR}" ]]; then
    rm -rf -- "${LOCK_DIR}"
  fi
  exit "${exit_code}"
}
trap cleanup EXIT HUP INT TERM

usage() {
  cat >&2 <<'EOF'
Usage: scripts/recover_release.sh --current-state PATH --current-env-file PATH
       --previous-env-file PATH
       --state-dir PATH --smoke-email ADDRESS --smoke-password-file PATH
       --compatibility-evidence PATH
EOF
}

while (( $# > 0 )); do
  case "$1" in
    --current-state) CURRENT_STATE="$2"; shift ;;
    --current-env-file) CURRENT_ENV_FILE="$2"; shift ;;
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

[[ -r "${CURRENT_STATE}" && -r "${CURRENT_ENV_FILE}" && -r "${PREVIOUS_ENV_FILE}" && -n "${STATE_DIR}" \
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
LOCK_OWNED=true
printf '{"host":"%s","pid":%s,"operation":"recovery"}\n' "$(hostname)" "$$" \
  >"${LOCK_DIR}/owner.json"
chmod 600 "${LOCK_DIR}/owner.json"

current_preflight_args=(preflight --env-file "${CURRENT_ENV_FILE}" \
  --compose-file "${RELEASE_COMPOSE_FILE}")
preflight_args=(preflight --env-file "${PREVIOUS_ENV_FILE}" \
  --compose-file "${RELEASE_COMPOSE_FILE}" \
  --expected-checkout-revision "$(jq -r '.revision' "${CURRENT_STATE}")")
if [[ "${RELEASE_LOCAL_REHEARSAL:-false}" == true ]]; then
  current_preflight_args+=(--local-rehearsal)
  preflight_args+=(--local-rehearsal)
fi
current_preflight="$(python3 scripts/release_contract.py "${current_preflight_args[@]}" --check-images)"
current_backend_image="$(release_env_value "${CURRENT_ENV_FILE}" BACKEND_IMAGE)"
export RELEASE_LOG_RELEASE_ID="$(jq -r '.release_id' <<<"${current_preflight}")"
export RELEASE_LOG_REVISION="$(jq -r '.release_revision' <<<"${current_preflight}")"
[[ "$(jq -r '.release_id' <<<"${current_preflight}")" == "$(jq -r '.release_id' "${CURRENT_STATE}")" \
  && "$(jq -r '.release_revision' <<<"${current_preflight}")" == "$(jq -r '.revision' "${CURRENT_STATE}")" \
  && "${current_backend_image}" == "$(jq -r '.backend_image' "${CURRENT_STATE}")" \
  && "$(jq -r '.config_sha256' <<<"${current_preflight}")" == "$(jq -r '.config_sha256' "${CURRENT_STATE}")" ]] \
  || { echo "ERROR: current environment does not match current release authority" >&2; exit 1; }
jq -e '.stages | index("migration") != null' "${CURRENT_STATE}" >/dev/null \
  || { echo "ERROR: recovery requires recorded forward-migration authority" >&2; exit 1; }
compatibility_outcome="$(release_stage_outcome "${CURRENT_STATE}" compatibility)"
[[ "${compatibility_outcome}" == passed:* ]] \
  || { echo "ERROR: recovery requires an accepted compatibility receipt" >&2; exit 1; }
accepted_authority="${compatibility_outcome#passed:}"
python3 scripts/release_contract.py "${preflight_args[@]}" >/dev/null
previous_release_id="$(release_env_value "${PREVIOUS_ENV_FILE}" RELEASE_ID)"
[[ "$(jq -r '.previous_release_id' "${CURRENT_STATE}")" == "${previous_release_id}" ]] \
  || { echo "ERROR: previous environment does not match current release authority" >&2; exit 1; }
previous_revision="$(release_env_value "${PREVIOUS_ENV_FILE}" RELEASE_REVISION)"
previous_backend_image="$(release_env_value "${PREVIOUS_ENV_FILE}" BACKEND_IMAGE)"

compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${PREVIOUS_ENV_FILE}")
if [[ "${RELEASE_LOCAL_REHEARSAL:-false}" != true ]]; then
  "${compose[@]}" pull --policy always >/dev/null
fi
python3 scripts/release_contract.py "${preflight_args[@]}" --check-images >/dev/null
forward_alembic_revision="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
  'SELECT version_num FROM alembic_version')"
compatibility_authority="$(python3 scripts/release_contract.py compatibility-validate \
  --evidence "${COMPATIBILITY_EVIDENCE}" \
  --env-file "${CURRENT_ENV_FILE}" \
  --target-release-id "$(jq -r '.release_id' "${CURRENT_STATE}")" \
  --target-revision "$(jq -r '.revision' "${CURRENT_STATE}")" \
  --target-backend-image "$(jq -r '.backend_image' "${CURRENT_STATE}")" \
  --previous-release-id "${previous_release_id}" \
  --previous-revision "${previous_revision}" \
  --previous-backend-image "${previous_backend_image}" \
  --forward-alembic-revision "${forward_alembic_revision}" \
  --accepted-receipt-sha256 "${accepted_authority%%:*}" \
  --accepted-receipt-hmac "${accepted_authority#*:}")"
[[ "${compatibility_outcome}" == "passed:${compatibility_authority}" ]] \
  || { echo "ERROR: recovery compatibility receipt conflicts with release state" >&2; exit 1; }
compatibility_sha256="${compatibility_authority%%:*}"
"${compose[@]}" stop edge api worker frontend >/dev/null 2>&1 || true
"${compose[@]}" up -d --no-build --wait --wait-timeout 120 db redis api worker frontend >/dev/null
# Recovery never runs an Alembic downgrade. The accepted receipt was generated
# by this exact previous image against this forward schema; recheck its running
# API and report models before opening traffic.
"${compose[@]}" exec -T api python -c \
  'from urllib.request import urlopen; r=urlopen("http://127.0.0.1:8000/api/v1/health/ready",timeout=5); raise SystemExit(0 if r.status == 200 else 1)'
"${compose[@]}" exec -T api python - <<'PY'
import asyncio

from sqlalchemy import select

from app.db.session import get_engine
from app.models.report_issuance import ReportArtifact, ReportIssuance


async def main() -> None:
    engine = get_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(select(ReportIssuance).limit(1))
            await connection.execute(select(ReportArtifact).limit(1))
    finally:
        await engine.dispose()


asyncio.run(main())
PY
EDGE_OPEN=true
"${compose[@]}" up -d --no-build --wait --wait-timeout 120 edge >/dev/null
COMPOSE_PRODUCTION_FILE="${RELEASE_COMPOSE_FILE}" COMPOSE_ENV_FILE="${PREVIOUS_ENV_FILE}" \
  SMOKE_BASE_URL="$(release_env_value "${PREVIOUS_ENV_FILE}" PUBLIC_ORIGIN)" \
  scripts/release_smoke.sh --email "${SMOKE_EMAIL}" --password-file "${SMOKE_PASSWORD_FILE}" \
    --expected-database-revision "${forward_alembic_revision}"

python3 - "${STATE_DIR}/recovery-$(jq -r '.release_id' "${CURRENT_STATE}")-${previous_release_id}.json" \
  "$(jq -r '.release_id' "${CURRENT_STATE}")" "${previous_release_id}" "${compatibility_sha256}" <<'PY'
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

path, failed_release, recovered_release, evidence_sha256 = sys.argv[1:]
stable = {
    "schema_version": 1,
    "event": "release_recovery",
    "failed_release_id": failed_release,
    "recovered_release_id": recovered_release,
    "compatibility_evidence_sha256": evidence_sha256,
    "database_downgrade": False,
}
target = Path(path)
if target.exists():
    existing = json.loads(target.read_text())
    if any(existing.get(name) != value for name, value in stable.items()):
        raise SystemExit("ERROR: recovery retry authority conflicts with its receipt")
    raise SystemExit(0)
payload = {
    **stable,
    "recorded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
}
descriptor, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
temporary = Path(temporary_name)
try:
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        json.dump(payload, output, sort_keys=True, separators=(",", ":"))
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, target)
finally:
    temporary.unlink(missing_ok=True)
PY
EDGE_OPEN=false
release_log release_recovery passed
trap - EXIT HUP INT TERM
rm -rf -- "${LOCK_DIR}"
LOCK_DIR=""
LOCK_OWNED=false
