#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_common.sh"

release_require_commands docker git gpg jq openssl python3 sha256sum tar
cd "${RELEASE_REPO_ROOT}"

readonly REVISION="$(git rev-parse HEAD)"
readonly PREVIOUS_REVISION="b64d07a0d7dcf97eb2654345ce55642165a570cf"
readonly PREVIOUS_ALEMBIC_REVISION="0070_driver_vehicle_approval"
readonly FORWARD_ALEMBIC_REVISION="0071_report_issuances"
readonly PROJECT_NAME="cardvert-w403a-rehearsal"
readonly MINIO_CONTAINER="${PROJECT_NAME}-minio"
readonly MINIO_IMAGE="minio/minio@sha256:d249d1fb6966de4d8ad26c04754b545205ff15a62e4fd19ebd0f26fa5baacbc0"
readonly MC_IMAGE="minio/mc@sha256:fb8f773eac8ef9d6da0486d5dec2f42f219358bcb8de579d1623d518c9ebd4cc"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cardvert-w403a-rehearsal.XXXXXX")"
CURRENT_ENV_FILE="${TEMP_DIR}/current.env"
PREVIOUS_ENV_FILE="${TEMP_DIR}/previous.env"
STATE_DIR="${TEMP_DIR}/state"
RECOVERY_STATE_DIR="${TEMP_DIR}/recovery-state"
BACKUP_DIR="${TEMP_DIR}/backups"
export COMPOSE_PROJECT_NAME="${PROJECT_NAME}"
export RELEASE_LOCAL_REHEARSAL=true

cleanup() {
  local exit_code=$?
  set +e
  docker rm -f "${MINIO_CONTAINER}" >/dev/null 2>&1 || true
  docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${CURRENT_ENV_FILE}" \
    down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf -- "${TEMP_DIR}"
  exit "${exit_code}"
}
trap cleanup EXIT HUP INT TERM

release_log rehearsal_build starting
docker build --build-arg "VCS_REF=${REVISION}" -t "${PROJECT_NAME}-backend:local" . >/dev/null
docker build --build-arg "VCS_REF=${REVISION}" -t "${PROJECT_NAME}-frontend:local" frontend >/dev/null
backend_image="$(docker image inspect "${PROJECT_NAME}-backend:local" --format '{{.Id}}')"
frontend_image="$(docker image inspect "${PROJECT_NAME}-frontend:local" --format '{{.Id}}')"

previous_context="${TEMP_DIR}/previous-context"
mkdir -p "${previous_context}"
git archive "${PREVIOUS_REVISION}" | tar -x -C "${previous_context}"
install -m 644 Dockerfile requirements-production.txt "${previous_context}/"
install -m 644 frontend/Dockerfile "${previous_context}/frontend/Dockerfile"
docker build --build-arg "VCS_REF=${PREVIOUS_REVISION}" \
  -t "${PROJECT_NAME}-previous-backend:local" "${previous_context}" >/dev/null
docker build --build-arg "VCS_REF=${PREVIOUS_REVISION}" \
  -t "${PROJECT_NAME}-previous-frontend:local" "${previous_context}/frontend" >/dev/null
previous_backend_image="$(docker image inspect "${PROJECT_NAME}-previous-backend:local" --format '{{.Id}}')"
previous_frontend_image="$(docker image inspect "${PROJECT_NAME}-previous-frontend:local" --format '{{.Id}}')"

database_password="Db-$(openssl rand -hex 24)"
redis_password="Redis-$(openssl rand -hex 24)"
jwt_secret="Jwt-$(openssl rand -hex 32)"
storage_secret="Storage-$(openssl rand -hex 24)"
storage_access="rehearsal-$(openssl rand -hex 12)"
keyring="$(openssl rand -base64 32 | tr -d '\n')"
previous_release_id="20260827T120000Z-rehearsal-previous"
current_release_id="$(date -u +%Y%m%dT%H%M%SZ)-rehearsal-current"
passphrase_file="${TEMP_DIR}/backup-passphrase"
smoke_password_file="${TEMP_DIR}/smoke-password"
printf 'Backup-%s\n' "$(openssl rand -hex 32)" >"${passphrase_file}"
printf 'Smoke-%s\n' "$(openssl rand -hex 24)" >"${smoke_password_file}"
chmod 600 "${passphrase_file}" "${smoke_password_file}"

write_environment() {
  local path="$1"
  local release_id="$2"
  local release_revision="$3"
  local predecessor="$4"
  local selected_backend="$5"
  local selected_frontend="$6"
  cat >"${path}" <<EOF
ENVIRONMENT=rehearsal
RELEASE_ID=${release_id}
RELEASE_REVISION=${release_revision}
PREVIOUS_RELEASE_ID=${predecessor}
BACKEND_IMAGE=${selected_backend}
FRONTEND_IMAGE=${selected_frontend}
POSTGIS_IMAGE=postgis/postgis@sha256:44126d872ac91993766c341e369c539e8196614321765d36a6f1bab0419a5fa5
REDIS_IMAGE=redis@sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf
CADDY_IMAGE=caddy@sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17
EDGE_HOSTNAME=cardvert.rehearsal.localhost
PUBLIC_ORIGIN=https://cardvert.rehearsal.localhost
BACKEND_CORS_ORIGINS=[]
SESSION_COOKIE_NAME=__Host-cardvert_session
POSTGRES_PASSWORD=${database_password}
DATABASE_URL=postgresql+asyncpg://mobility:${database_password}@db:5432/mobility
REDIS_PASSWORD=${redis_password}
REDIS_URL=redis://:${redis_password}@redis:6379/0
JWT_SECRET_KEY=${jwt_secret}
PAYOUT_CRYPTO_KEYRING_B64={"1":"${keyring}"}
PAYOUT_CRYPTO_KEY_VERSION=1
OBJECT_STORAGE_ENDPOINT_URL=http://${MINIO_CONTAINER}:9000
OBJECT_STORAGE_PUBLIC_ENDPOINT_URL=http://${MINIO_CONTAINER}:9000
OBJECT_STORAGE_REGION=local-rehearsal-1
OBJECT_STORAGE_BUCKET=cardvert-private-rehearsal
OBJECT_STORAGE_ACCESS_KEY_ID=${storage_access}
OBJECT_STORAGE_SECRET_ACCESS_KEY=${storage_secret}
ALLOW_DEMO_SEED=false
DEMO_LOGIN_ENABLED=false
PRIVACY_DISCLOSURE_SYNTHETIC_TEST_MODE=false
PRIVACY_DISCLOSURE_LIVE_AUTHORIZED=false
MEASUREMENT_LIVE_ISSUANCE_AUTHORIZED=false
LOGIN_RATE_LIMIT_RELAY_CLIENT_IP_HEADER=false
LOGIN_RATE_LIMIT_TRUST_CLIENT_IP_HEADER=false
LOGIN_RATE_LIMIT_TRUSTED_PROXY_CIDRS=
BACKUP_PASSPHRASE_FILE=${passphrase_file}
BACKUP_RETENTION_DAYS=35
SENTRY_DSN=
LOG_LEVEL=INFO
EOF
  chmod 600 "${path}"
}

write_environment "${CURRENT_ENV_FILE}" "${current_release_id}" "${REVISION}" \
  "${previous_release_id}" "${backend_image}" "${frontend_image}"
write_environment "${PREVIOUS_ENV_FILE}" "${previous_release_id}" "${PREVIOUS_REVISION}" "" \
  "${previous_backend_image}" "${previous_frontend_image}"

docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${CURRENT_ENV_FILE}" \
  create db redis >/dev/null
docker run -d --name "${MINIO_CONTAINER}" --network "${PROJECT_NAME}_data" \
  -e "MINIO_ROOT_USER=${storage_access}" -e "MINIO_ROOT_PASSWORD=${storage_secret}" \
  "${MINIO_IMAGE}" server /data >/dev/null
docker run --rm --network "${PROJECT_NAME}_data" --entrypoint /bin/sh \
  -e "MC_HOST_rehearsal=http://${storage_access}:${storage_secret}@${MINIO_CONTAINER}:9000" \
  "${MC_IMAGE}" -c \
  'until mc ready rehearsal; do sleep 1; done; mc mb --ignore-existing rehearsal/cardvert-private-rehearsal; mc version enable rehearsal/cardvert-private-rehearsal; mc anonymous set none rehearsal/cardvert-private-rehearsal' \
  >/dev/null

mkdir -p "${STATE_DIR}" "${RECOVERY_STATE_DIR}" "${BACKUP_DIR}"
release_log rehearsal_predecessor_fixture starting
compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${PREVIOUS_ENV_FILE}")
"${compose[@]}" up -d --wait --wait-timeout 120 db redis >/dev/null
"${compose[@]}" --profile release run --rm -T --no-deps migrate
"${compose[@]}" up -d --no-build --wait --wait-timeout 120 \
  db redis api worker frontend >/dev/null
"${compose[@]}" up -d --no-build edge >/dev/null
COMPOSE_PRODUCTION_FILE="${RELEASE_COMPOSE_FILE}" COMPOSE_ENV_FILE="${PREVIOUS_ENV_FILE}" \
  SMOKE_BASE_URL="$(release_env_value "${PREVIOUS_ENV_FILE}" PUBLIC_ORIGIN)" \
  scripts/release_smoke.sh --expect-empty-user-table
[[ "$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
  'SELECT version_num FROM alembic_version')" == "${PREVIOUS_ALEMBIC_REVISION}" ]] \
  || { echo "ERROR: predecessor fixture did not reach its exact migration head" >&2; exit 1; }
release_log rehearsal_predecessor_fixture passed
smoke_password="$(<"${smoke_password_file}")"
password_hash="$("${compose[@]}" exec -T -e "SMOKE_PASSWORD=${smoke_password}" api python -c \
  'import os; from app.core.security import hash_password; print(hash_password(os.environ["SMOKE_PASSWORD"]))')"
payload="${TEMP_DIR}/synthetic-report.txt"
printf 'synthetic Cardvert recovery evidence\n' >"${payload}"
payload_sha="$(sha256sum "${payload}" | awk '{print $1}')"
payload_bytes="$(wc -c <"${payload}" | tr -d '[:space:]')"
docker run --rm --network "${PROJECT_NAME}_data" --entrypoint /bin/sh \
  -e "MC_HOST_rehearsal=http://${storage_access}:${storage_secret}@${MINIO_CONTAINER}:9000" \
  -v "${payload}:/tmp/synthetic-report.txt:ro" "${MC_IMAGE}" -c \
  'mc cp /tmp/synthetic-report.txt rehearsal/cardvert-private-rehearsal/rehearsal/report.txt' \
  >/dev/null
"${compose[@]}" exec -T db psql -U mobility -d mobility -v ON_ERROR_STOP=1 \
  -v "password_hash=${password_hash}" -v "payload_bytes=${payload_bytes}" \
  -v "payload_sha=${payload_sha}" <<'SQL' >/dev/null
INSERT INTO users (id,email,password_hash,full_name,role,status)
VALUES ('80000000-0000-4000-8000-000000000001','rehearsal@example.invalid',:'password_hash','Rehearsal User','advertiser','active');
INSERT INTO advertiser_organizations (id,name,status)
VALUES ('80000000-0000-4000-8000-000000000002','Synthetic Rehearsal','active');
INSERT INTO file_upload_intents
  (id,organization_id,uploader_user_id,client_request_id,request_fingerprint,purpose,
   original_filename,declared_content_type,declared_size_bytes,declared_sha256,object_key,
   expires_at,status)
VALUES
  ('80000000-0000-4000-8000-000000000004','80000000-0000-4000-8000-000000000002',
   '80000000-0000-4000-8000-000000000001','80000000-0000-4000-8000-000000000005',
   repeat('a',64),'creative','synthetic-report.txt','text/plain',:'payload_bytes',:'payload_sha',
   'rehearsal/report.txt',clock_timestamp() + interval '1 hour','confirmed');
INSERT INTO stored_files
  (id,upload_intent_id,organization_id,uploader_user_id,purpose,original_filename,storage_key,
   content_type,size_bytes,checksum_sha256,scan_status)
VALUES
  ('80000000-0000-4000-8000-000000000003','80000000-0000-4000-8000-000000000004',
   '80000000-0000-4000-8000-000000000002','80000000-0000-4000-8000-000000000001',
   'creative','synthetic-report.txt',
   'rehearsal/report.txt','text/plain',:'payload_bytes',:'payload_sha','clean');
SQL

release_compatibility="${TEMP_DIR}/release-compatibility.json"
jq -n \
  --arg release "${current_release_id}" --arg revision "${REVISION}" \
  --arg image "${backend_image}" --arg previous_release "${previous_release_id}" \
  --arg previous_revision "${PREVIOUS_REVISION}" --arg previous_image "${previous_backend_image}" \
  --arg migration "${FORWARD_ALEMBIC_REVISION}" \
  '{schema_version:1,result:"passed",target_release_id:$release,target_revision:$revision,
    target_backend_image:$image,previous_release_id:$previous_release,
    previous_revision:$previous_revision,previous_backend_image:$previous_image,
    forward_alembic_revision:$migration,
    checks:{no_database_downgrade:true,previous_image_readiness:true,
      previous_image_report_schema_canary:true}}' >"${release_compatibility}"
chmod 600 "${release_compatibility}"

release_log rehearsal_populated_forward_release starting
scripts/release.sh --env-file "${CURRENT_ENV_FILE}" --state-dir "${STATE_DIR}" \
  --backup-dir "${BACKUP_DIR}" --smoke-email "rehearsal@example.invalid" \
  --smoke-password-file "${smoke_password_file}" \
  --compatibility-evidence "${release_compatibility}"
# Retry proves the authenticated backup and ordered release state converge.
scripts/release.sh --env-file "${CURRENT_ENV_FILE}" --state-dir "${STATE_DIR}" \
  --backup-dir "${BACKUP_DIR}" --smoke-email "rehearsal@example.invalid" \
  --smoke-password-file "${smoke_password_file}" \
  --compatibility-evidence "${release_compatibility}"
compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${CURRENT_ENV_FILE}")

"${compose[@]}" exec -T api python - <<'PY'
import concurrent.futures
import statistics
import time
from urllib.request import urlopen

def request(_):
    started = time.perf_counter()
    with urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
        if response.status != 200:
            raise RuntimeError("health request failed")
    return (time.perf_counter() - started) * 1000

with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
    durations = list(pool.map(request, range(100)))
p95 = statistics.quantiles(durations, n=20)[18]
if p95 >= 500:
    raise SystemExit(f"bounded load failed: p95={p95:.2f}ms")
print(f'{{"event":"bounded_load","status":"passed","requests":100,"p95_ms":{p95:.2f}}}')
PY

recovery_state_file="${STATE_DIR}/${current_release_id}.json"
bundle="${BACKUP_DIR}/${current_release_id}.tar.gpg"
scripts/verify_restore.sh --env-file "${CURRENT_ENV_FILE}" \
  --bundle "${bundle}" --passphrase-file "${passphrase_file}"
# Re-verify the same immutable artifact to exercise retry authority.
scripts/verify_restore.sh --env-file "${CURRENT_ENV_FILE}" \
  --bundle "${bundle}" --passphrase-file "${passphrase_file}"
"${compose[@]}" run --rm -T --no-deps api python - <<'PY'
from app.operations.storage_snapshot import _client
from app.core.config import get_settings

client = _client()
settings = get_settings()
pages = client.get_paginator("list_object_versions").paginate(
    Bucket=settings.object_storage_bucket, Prefix="restore-verification/"
)
if any(page.get("Versions") or page.get("DeleteMarkers") for page in pages):
    raise SystemExit("restore verification left private object versions behind")
print('{"event":"restore_object_cleanup","status":"passed"}')
PY

recovery_compatibility="${TEMP_DIR}/recovery-compatibility.json"
jq -n \
  --arg release "${current_release_id}" --arg revision "${REVISION}" \
  --arg image "${backend_image}" --arg previous_release "${previous_release_id}" \
  --arg previous_revision "${PREVIOUS_REVISION}" --arg previous_image "${previous_backend_image}" \
  --arg migration "${FORWARD_ALEMBIC_REVISION}" \
  '{schema_version:1,result:"passed",target_release_id:$release,target_revision:$revision,
    target_backend_image:$image,previous_release_id:$previous_release,
    previous_revision:$previous_revision,previous_backend_image:$previous_image,
    forward_alembic_revision:$migration,
    checks:{no_database_downgrade:true,previous_image_readiness:true,
      previous_image_report_schema_canary:true}}' >"${recovery_compatibility}"
chmod 600 "${recovery_compatibility}"

release_log rehearsal_distinct_previous_recovery starting
scripts/recover_release.sh --current-state "${recovery_state_file}" \
  --current-env-file "${CURRENT_ENV_FILE}" \
  --previous-env-file "${PREVIOUS_ENV_FILE}" --state-dir "${RECOVERY_STATE_DIR}" \
  --smoke-email "rehearsal@example.invalid" --smoke-password-file "${smoke_password_file}" \
  --compatibility-evidence "${recovery_compatibility}"
db_revision_after_recovery="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
  'SELECT version_num FROM alembic_version')"
[[ "${db_revision_after_recovery}" == "${FORWARD_ALEMBIC_REVISION}" ]] \
  || { echo "ERROR: recovery implied a migration downgrade" >&2; exit 1; }
release_log recovery_distinct_previous_revision passed

# An invalid smoke identity fails after edge open and must close the edge in
# the release trap while retaining the forward database.
if scripts/release.sh --env-file "${CURRENT_ENV_FILE}" --state-dir "${STATE_DIR}" \
  --backup-dir "${BACKUP_DIR}" --smoke-email "missing@example.invalid" \
  --smoke-password-file "${smoke_password_file}" \
  --compatibility-evidence "${release_compatibility}"; then
  echo "ERROR: deliberate post-edge smoke failure unexpectedly passed" >&2
  exit 1
fi
if "${compose[@]}" ps --status running --services | grep -qx edge; then
  echo "ERROR: release failure left public edge traffic open" >&2
  exit 1
fi
release_log traffic_failure_stop passed
release_log rehearsal passed
