#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_common.sh"

ENV_FILE=""
STATE_FILE=""
OUTPUT_DIR=""
TEMP_DIR=""
GPG_HOME=""
WRITERS_STOPPED=false
LEAVE_WRITERS_STOPPED=false
RUNNING_SERVICES=""

usage() {
  echo "Usage: scripts/backup_release.sh --env-file PATH --state-file PATH --output-dir PATH [--leave-writers-stopped]" >&2
}

cleanup() {
  local exit_code=$?
  set +e
  if [[ "${WRITERS_STOPPED}" == true ]]; then
    while IFS= read -r service; do
      [[ -n "${service}" ]] || continue
      docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${ENV_FILE}" start "${service}" >/dev/null
    done <<<"${RUNNING_SERVICES}"
  fi
  [[ -z "${TEMP_DIR}" ]] || rm -rf -- "${TEMP_DIR}"
  [[ -z "${GPG_HOME}" ]] || rm -rf -- "${GPG_HOME}"
  exit "${exit_code}"
}
trap cleanup EXIT HUP INT TERM

while (( $# > 0 )); do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift ;;
    --state-file) STATE_FILE="$2"; shift ;;
    --output-dir) OUTPUT_DIR="$2"; shift ;;
    --leave-writers-stopped) LEAVE_WRITERS_STOPPED=true ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
  shift
done

[[ -r "${ENV_FILE}" && -r "${STATE_FILE}" && -n "${OUTPUT_DIR}" ]] || { usage; exit 2; }
release_require_commands docker gpg jq python3 sha256sum tar
cd "${RELEASE_REPO_ROOT}"

preflight_args=(preflight --env-file "${ENV_FILE}" --compose-file "${RELEASE_COMPOSE_FILE}")
if [[ "${RELEASE_LOCAL_REHEARSAL:-false}" == true ]]; then
  preflight_args+=(--local-rehearsal)
fi
preflight="$(python3 scripts/release_contract.py "${preflight_args[@]}")"
release_id="$(release_env_value "${ENV_FILE}" RELEASE_ID)"
release_revision="$(release_env_value "${ENV_FILE}" RELEASE_REVISION)"
export RELEASE_LOG_RELEASE_ID="${release_id}"
export RELEASE_LOG_REVISION="${release_revision}"
passphrase_file="$(release_env_value "${ENV_FILE}" BACKUP_PASSPHRASE_FILE)"
retention_days="$(release_env_value "${ENV_FILE}" BACKUP_RETENTION_DAYS)"
config_sha256="$(jq -r '.config_sha256' <<<"${preflight}")"
[[ "$(jq -r '.release_id' "${STATE_FILE}")" == "${release_id}" ]] \
  || { echo "ERROR: release state does not match environment" >&2; exit 2; }

mkdir -p -- "${OUTPUT_DIR}"
chmod 700 "${OUTPUT_DIR}"
OUTPUT_DIR="$(cd "${OUTPUT_DIR}" && pwd)"
TEMP_DIR="$(mktemp -d "${OUTPUT_DIR}/.${release_id}.backup.XXXXXX")"
chmod 700 "${TEMP_DIR}"
GPG_HOME="$(mktemp -d /tmp/cardvert-gpg.XXXXXX)"
chmod 700 "${GPG_HOME}"
export GNUPGHOME="${GPG_HOME}"

compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${ENV_FILE}")
RUNNING_SERVICES="$("${compose[@]}" ps --status running --services)"
release_log backup_quiesce starting
WRITERS_STOPPED=true
"${compose[@]}" stop edge frontend api worker >/dev/null

release_log backup_database starting
"${compose[@]}" exec -T db pg_dump -U mobility -d mobility --format=custom >"${TEMP_DIR}/database.dump"
alembic_revision="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc 'SELECT version_num FROM alembic_version')"
postgis_version="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc "SELECT extversion FROM pg_extension WHERE extname='postgis'")"
database_marker="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc "SELECT to_char(clock_timestamp() AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') || '/' || pg_current_wal_lsn()")"
[[ -n "${alembic_revision}" && -n "${postgis_version}" && -n "${database_marker}" ]] \
  || { echo "ERROR: database revision/marker/PostGIS evidence is incomplete" >&2; exit 1; }

release_log backup_storage starting
"${compose[@]}" run --rm -T --no-deps api \
  python -m app.operations.storage_snapshot export >"${TEMP_DIR}/objects.tar"
tar -xOf "${TEMP_DIR}/objects.tar" inventory.json >"${TEMP_DIR}/inventory.json"
python3 - "${TEMP_DIR}/inventory.json" "${TEMP_DIR}/manifest-objects.json" <<'PY'
import json
import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
inventory = json.loads(source.read_text())
objects = [
    {
        "key": item["key"],
        "version_id": item["version_id"],
        "sha256": item["sha256"],
        "bytes": item["bytes"],
    }
    for item in inventory
]
destination.write_text(json.dumps(objects, sort_keys=True, separators=(",", ":")))
PY

database_sha256="$(sha256sum "${TEMP_DIR}/database.dump" | awk '{print $1}')"
database_bytes="$(wc -c <"${TEMP_DIR}/database.dump" | tr -d '[:space:]')"
created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
manifest_sha256="$(python3 scripts/release_contract.py backup-manifest \
  --release-id "${release_id}" \
  --release-revision "${release_revision}" \
  --config-sha256 "${config_sha256}" \
  --alembic-revision "${alembic_revision}" \
  --database-sha256 "${database_sha256}" \
  --database-bytes "${database_bytes}" \
  --database-marker "${database_marker}" \
  --objects-json "${TEMP_DIR}/manifest-objects.json" \
  --retention-days "${retention_days}" \
  --created-at "${created_at}" \
  --output "${TEMP_DIR}/manifest.json")"
install -m 600 "${STATE_FILE}" "${TEMP_DIR}/release-state.json"

partial_bundle="${OUTPUT_DIR}/${release_id}.tar.gpg.partial"
final_bundle="${OUTPUT_DIR}/${release_id}.tar.gpg"
rm -f -- "${partial_bundle}"
release_log backup_encrypt starting
tar -C "${TEMP_DIR}" -cf - manifest.json release-state.json database.dump objects.tar \
  | gpg --batch --yes --pinentry-mode loopback --passphrase-file "${passphrase_file}" \
      --symmetric --cipher-algo AES256 --output "${partial_bundle}"
chmod 600 "${partial_bundle}"
bundle_sha256="$(sha256sum "${partial_bundle}" | awk '{print $1}')"
mv -- "${partial_bundle}" "${final_bundle}"
printf '%s  %s\n' "${bundle_sha256}" "$(basename "${final_bundle}")" \
  >"${final_bundle}.sha256.partial"
chmod 600 "${final_bundle}.sha256.partial"
mv -- "${final_bundle}.sha256.partial" "${final_bundle}.sha256"
python3 - "${final_bundle}.complete.json.partial" "${release_id}" "${release_revision}" \
  "${config_sha256}" "${bundle_sha256}" "${manifest_sha256}" "${created_at}" \
  "${retention_days}" <<'PY'
import json
import os
import sys
from datetime import UTC, datetime, timedelta

(
    path,
    release_id,
    release_revision,
    config_digest,
    bundle_digest,
    manifest_digest,
    created_at,
    retention_days,
) = sys.argv[1:]
created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
payload = {
    "schema_version": 1,
    "state": "complete",
    "release_id": release_id,
    "release_revision": release_revision,
    "config_sha256": config_digest,
    "bundle_sha256": bundle_digest,
    "manifest_sha256": manifest_digest,
    "created_at": created.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    "expires_at": (created + timedelta(days=int(retention_days))).astimezone(UTC).isoformat().replace("+00:00", "Z"),
}
descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    json.dump(payload, output, sort_keys=True, separators=(",", ":"))
    output.write("\n")
PY
mv -- "${final_bundle}.complete.json.partial" "${final_bundle}.complete.json"

if [[ "${LEAVE_WRITERS_STOPPED}" != true ]]; then
  while IFS= read -r service; do
    [[ -n "${service}" ]] || continue
    "${compose[@]}" start "${service}" >/dev/null
  done <<<"${RUNNING_SERVICES}"
fi
WRITERS_STOPPED=false
release_log backup_complete passed
trap - EXIT HUP INT TERM
rm -rf -- "${TEMP_DIR}"
TEMP_DIR=""
rm -rf -- "${GPG_HOME}"
GPG_HOME=""
