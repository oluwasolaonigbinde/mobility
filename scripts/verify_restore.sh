#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_common.sh"

ENV_FILE=""
BUNDLE=""
PASSPHRASE_FILE=""
TEMP_DIR=""
GPG_HOME=""
RESTORE_DB=""

usage() {
  echo "Usage: scripts/verify_restore.sh --env-file PATH --bundle PATH --passphrase-file PATH" >&2
}

cleanup() {
  local exit_code=$?
  set +e
  if [[ -n "${RESTORE_DB}" ]]; then
    docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T db \
      dropdb -U mobility --if-exists "${RESTORE_DB}" >/dev/null 2>&1
  fi
  [[ -z "${TEMP_DIR}" ]] || rm -rf -- "${TEMP_DIR}"
  [[ -z "${GPG_HOME}" ]] || rm -rf -- "${GPG_HOME}"
  exit "${exit_code}"
}
trap cleanup EXIT HUP INT TERM

while (( $# > 0 )); do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift ;;
    --bundle) BUNDLE="$2"; shift ;;
    --passphrase-file) PASSPHRASE_FILE="$2"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
  shift
done

[[ -r "${ENV_FILE}" && -r "${BUNDLE}" && -r "${PASSPHRASE_FILE}" ]] || { usage; exit 2; }
release_require_commands docker gpg jq python3 sha256sum tar
cd "${RELEASE_REPO_ROOT}"
preflight_args=(preflight --env-file "${ENV_FILE}" --compose-file "${RELEASE_COMPOSE_FILE}")
if [[ "${RELEASE_LOCAL_REHEARSAL:-false}" == true ]]; then
  preflight_args+=(--local-rehearsal)
fi
preflight="$(python3 scripts/release_contract.py "${preflight_args[@]}")"
expected_release_id="$(jq -r '.release_id' <<<"${preflight}")"
expected_release_revision="$(jq -r '.release_revision' <<<"${preflight}")"
export RELEASE_LOG_RELEASE_ID="${expected_release_id}"
export RELEASE_LOG_REVISION="${expected_release_revision}"
expected_config_sha256="$(jq -r '.config_sha256' <<<"${preflight}")"

BUNDLE="$(cd "$(dirname "${BUNDLE}")" && pwd)/$(basename "${BUNDLE}")"
[[ -r "${BUNDLE}.sha256" && -r "${BUNDLE}.complete.json" ]] \
  || { echo "ERROR: backup digest or complete marker is missing" >&2; exit 1; }
read -r expected_digest expected_filename <"${BUNDLE}.sha256"
[[ "${expected_filename}" == "$(basename "${BUNDLE}")" ]] \
  || { echo "ERROR: backup digest sidecar names the wrong bundle" >&2; exit 1; }
observed_digest="$(sha256sum "${BUNDLE}" | awk '{print $1}')"
[[ "${expected_digest}" == "${observed_digest}" ]] \
  || { echo "ERROR: encrypted backup digest mismatch" >&2; exit 1; }
[[ "$(jq -r '.bundle_sha256 // empty' "${BUNDLE}.complete.json")" == "${observed_digest}" ]] \
  || { echo "ERROR: backup complete marker does not bind the ciphertext" >&2; exit 1; }

TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cardvert-restore-verify.XXXXXX")"
chmod 700 "${TEMP_DIR}"
GPG_HOME="$(mktemp -d /tmp/cardvert-gpg.XXXXXX)"
chmod 700 "${GPG_HOME}"
export GNUPGHOME="${GPG_HOME}"
gpg --batch --yes --pinentry-mode loopback --passphrase-file "${PASSPHRASE_FILE}" \
  --decrypt --output "${TEMP_DIR}/bundle.tar" "${BUNDLE}"
members="$(tar -tf "${TEMP_DIR}/bundle.tar" | sort)"
expected_members=$'database.dump\nmanifest.json\nobjects.tar\nrelease-state.json'
[[ "${members}" == "${expected_members}" ]] \
  || { echo "ERROR: recovery bundle contains missing or extra members" >&2; exit 1; }
tar -C "${TEMP_DIR}" -xf "${TEMP_DIR}/bundle.tar"
python3 scripts/release_contract.py manifest-validate --manifest "${TEMP_DIR}/manifest.json" >/dev/null
python3 scripts/release_contract.py backup-authority-validate \
  --complete-marker "${BUNDLE}.complete.json" --manifest "${TEMP_DIR}/manifest.json" \
  --release-state "${TEMP_DIR}/release-state.json" --bundle-sha256 "${observed_digest}" \
  --expected-release-id "${expected_release_id}" \
  --expected-release-revision "${expected_release_revision}" \
  --expected-config-sha256 "${expected_config_sha256}" >/dev/null
manifest_database_sha="$(jq -r '.database_sha256' "${TEMP_DIR}/manifest.json")"
[[ "$(sha256sum "${TEMP_DIR}/database.dump" | awk '{print $1}')" == "${manifest_database_sha}" ]] \
  || { echo "ERROR: restored database dump digest mismatch" >&2; exit 1; }
[[ "$(wc -c <"${TEMP_DIR}/database.dump" | tr -d '[:space:]')" \
  == "$(jq -r '.database_bytes' "${TEMP_DIR}/manifest.json")" ]] \
  || { echo "ERROR: restored database dump size mismatch" >&2; exit 1; }
tar -xOf "${TEMP_DIR}/objects.tar" inventory.json >"${TEMP_DIR}/inventory.json"
python3 - "${TEMP_DIR}/manifest.json" "${TEMP_DIR}/inventory.json" <<'PY'
import json
import sys
from pathlib import Path

manifest, inventory = (json.loads(Path(path).read_text()) for path in sys.argv[1:])
manifest_objects = {(item["key"], item["version_id"], item["sha256"], item["bytes"]) for item in manifest["objects"]}
inventory_objects = {(item["key"], item["version_id"], item["sha256"], item["bytes"]) for item in inventory}
if manifest_objects != inventory_objects:
    raise SystemExit("object archive inventory disagrees with authenticated manifest")
PY

release_id="$(jq -r '.release_id' "${TEMP_DIR}/manifest.json")"
RESTORE_DB="cardvert_restore_verify_$(printf '%s' "${release_id}" | sha256sum | cut -c1-16)"
compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${ENV_FILE}")
"${compose[@]}" exec -T db createdb -U mobility "${RESTORE_DB}"
"${compose[@]}" exec -T db pg_restore -U mobility -d "${RESTORE_DB}" --no-owner --exit-on-error \
  <"${TEMP_DIR}/database.dump"
db_revision="$("${compose[@]}" exec -T db psql -U mobility -d "${RESTORE_DB}" -Atc 'SELECT version_num FROM alembic_version')"
postgis_version="$("${compose[@]}" exec -T db psql -U mobility -d "${RESTORE_DB}" -Atc "SELECT extversion FROM pg_extension WHERE extname='postgis'")"
snapshot_revision="$(jq -r '.alembic_revision' "${TEMP_DIR}/manifest.json")"
[[ "${db_revision}" == "${snapshot_revision}" && -n "${postgis_version}" ]] \
  || { echo "ERROR: isolated restore is not compatible with the exact release image" >&2; exit 1; }
"${compose[@]}" run --rm -T --no-deps -e "SNAPSHOT_REVISION=${snapshot_revision}" api python - <<'PY'
import os
from alembic.config import Config
from alembic.script import ScriptDirectory

scripts = ScriptDirectory.from_config(Config("alembic.ini"))
heads = scripts.get_heads()
known_revisions = {revision.revision for revision in scripts.walk_revisions()}
if len(heads) != 1 or os.environ["SNAPSHOT_REVISION"] not in known_revisions:
    raise SystemExit("restored migration revision is not in the exact release image graph")
PY

database_url="$(release_env_value "${ENV_FILE}" DATABASE_URL)"
restore_url="$(DATABASE_URL_TO_REWRITE="${database_url}" RESTORE_DATABASE_NAME="${RESTORE_DB}" \
  python3 -c 'import os; from scripts.release_contract import database_url_for_name; print(database_url_for_name(os.environ["DATABASE_URL_TO_REWRITE"], os.environ["RESTORE_DATABASE_NAME"]))')"
restore_nonce="$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
"${compose[@]}" run --rm -T --no-deps \
  -e DATABASE_URL="${restore_url}" \
  -v "${TEMP_DIR}/objects.tar:/tmp/objects.tar:ro" \
  api python -m app.operations.storage_snapshot verify \
    --archive /tmp/objects.tar --restore-prefix "restore-verification/${release_id}/${restore_nonce}"

release_log restore_isolated passed
trap - EXIT HUP INT TERM
"${compose[@]}" exec -T db dropdb -U mobility "${RESTORE_DB}"
RESTORE_DB=""
rm -rf -- "${TEMP_DIR}"
TEMP_DIR=""
rm -rf -- "${GPG_HOME}"
GPG_HOME=""
