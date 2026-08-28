#!/usr/bin/env bash

set -Eeuo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/release_common.sh"

release_require_commands docker gpg jq openssl python3 sha256sum
cd "${RELEASE_REPO_ROOT}"

readonly REVISION="$(git rev-parse HEAD)"
readonly PROJECT_NAME="cardvert-w403a-rehearsal"
readonly MINIO_CONTAINER="${PROJECT_NAME}-minio"
readonly MINIO_IMAGE="minio/minio@sha256:d249d1fb6966de4d8ad26c04754b545205ff15a62e4fd19ebd0f26fa5baacbc0"
readonly MC_IMAGE="minio/mc@sha256:fb8f773eac8ef9d6da0486d5dec2f42f219358bcb8de579d1623d518c9ebd4cc"
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/cardvert-w403a-rehearsal.XXXXXX")"
ENV_FILE="${TEMP_DIR}/rehearsal.env"
STATE_DIR="${TEMP_DIR}/state"
BACKUP_DIR="${TEMP_DIR}/backups"
export COMPOSE_PROJECT_NAME="${PROJECT_NAME}"
export RELEASE_LOCAL_REHEARSAL=true

cleanup() {
  local exit_code=$?
  set +e
  docker rm -f "${MINIO_CONTAINER}" >/dev/null 2>&1 || true
  docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${ENV_FILE}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf -- "${TEMP_DIR}"
  exit "${exit_code}"
}
trap cleanup EXIT HUP INT TERM

release_log rehearsal_build starting
docker build --build-arg "VCS_REF=${REVISION}" -t "${PROJECT_NAME}-backend:local" . >/dev/null
docker build --build-arg "VCS_REF=${REVISION}" -t "${PROJECT_NAME}-frontend:local" frontend >/dev/null
backend_image="$(docker image inspect "${PROJECT_NAME}-backend:local" --format '{{.Id}}')"
frontend_image="$(docker image inspect "${PROJECT_NAME}-frontend:local" --format '{{.Id}}')"
database_password="Db-$(openssl rand -hex 24)"
redis_password="Redis-$(openssl rand -hex 24)"
jwt_secret="Jwt-$(openssl rand -hex 32)"
storage_secret="Storage-$(openssl rand -hex 24)"
storage_access="rehearsal-$(openssl rand -hex 12)"
keyring="$(openssl rand -base64 32 | tr -d '\n')"
release_id="$(date -u +%Y%m%dT%H%M%SZ)-rehearsal"
passphrase_file="${TEMP_DIR}/backup-passphrase"
printf 'Backup-%s\n' "$(openssl rand -hex 32)" >"${passphrase_file}"
chmod 600 "${passphrase_file}"

cat >"${ENV_FILE}" <<EOF
ENVIRONMENT=rehearsal
RELEASE_ID=${release_id}
RELEASE_REVISION=${REVISION}
PREVIOUS_RELEASE_ID=
BACKEND_IMAGE=${backend_image}
FRONTEND_IMAGE=${frontend_image}
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
EOF
chmod 600 "${ENV_FILE}"

python3 scripts/release_contract.py preflight --local-rehearsal --check-images \
  --env-file "${ENV_FILE}" --compose-file "${RELEASE_COMPOSE_FILE}" >/dev/null
compose=(docker compose -f "${RELEASE_COMPOSE_FILE}" --env-file "${ENV_FILE}")
"${compose[@]}" up -d --wait --wait-timeout 120 db redis >/dev/null

docker run -d --name "${MINIO_CONTAINER}" --network "${PROJECT_NAME}_data" \
  -e "MINIO_ROOT_USER=${storage_access}" -e "MINIO_ROOT_PASSWORD=${storage_secret}" \
  "${MINIO_IMAGE}" server /data >/dev/null
docker run --rm --network "${PROJECT_NAME}_data" --entrypoint /bin/sh \
  -e "MC_HOST_rehearsal=http://${storage_access}:${storage_secret}@${MINIO_CONTAINER}:9000" \
  "${MC_IMAGE}" -c \
  'until mc ready rehearsal; do sleep 1; done; mc mb --ignore-existing rehearsal/cardvert-private-rehearsal; mc version enable rehearsal/cardvert-private-rehearsal; mc anonymous set none rehearsal/cardvert-private-rehearsal' \
  >/dev/null

"${compose[@]}" --profile release run --rm -T --no-deps migrate >/dev/null

payload="${TEMP_DIR}/synthetic-report.txt"
printf 'synthetic Cardvert recovery evidence\n' >"${payload}"
payload_sha="$(sha256sum "${payload}" | awk '{print $1}')"
payload_bytes="$(wc -c <"${payload}" | tr -d '[:space:]')"
docker run --rm --network "${PROJECT_NAME}_data" --entrypoint /bin/sh \
  -e "MC_HOST_rehearsal=http://${storage_access}:${storage_secret}@${MINIO_CONTAINER}:9000" \
  -v "${payload}:/tmp/synthetic-report.txt:ro" "${MC_IMAGE}" -c \
  'mc cp /tmp/synthetic-report.txt rehearsal/cardvert-private-rehearsal/rehearsal/report.txt' \
  >/dev/null
"${compose[@]}" exec -T db psql -U mobility -d mobility -v ON_ERROR_STOP=1 <<SQL >/dev/null
INSERT INTO users (id,email,password_hash,full_name,role,status)
VALUES ('80000000-0000-4000-8000-000000000001','rehearsal@example.invalid','not-a-login-hash','Rehearsal User','advertiser','active');
INSERT INTO advertiser_organizations (id,name,status)
VALUES ('80000000-0000-4000-8000-000000000002','Synthetic Rehearsal','active');
INSERT INTO stored_files
  (id,organization_id,uploader_user_id,purpose,original_filename,storage_key,content_type,size_bytes,checksum_sha256,scan_status)
VALUES
  ('80000000-0000-4000-8000-000000000003','80000000-0000-4000-8000-000000000002',
   '80000000-0000-4000-8000-000000000001','report_export','synthetic-report.txt',
   'rehearsal/report.txt','text/plain',${payload_bytes},'${payload_sha}','clean');
SQL

"${compose[@]}" up -d --wait --wait-timeout 120 api worker frontend >/dev/null
"${compose[@]}" exec -T api python -m app.operations.readiness --write-canary >/dev/null
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

mkdir -p "${STATE_DIR}" "${BACKUP_DIR}"
config_sha="$(python3 scripts/release_contract.py preflight --local-rehearsal \
  --env-file "${ENV_FILE}" --compose-file "${RELEASE_COMPOSE_FILE}" | jq -r '.config_sha256')"
state_file="${STATE_DIR}/${release_id}.json"
python3 scripts/release_contract.py state-init --state-file "${state_file}" \
  --release-id "${release_id}" --revision "${REVISION}" --backend-image "${backend_image}" \
  --frontend-image "${frontend_image}" --config-sha256 "${config_sha}" >/dev/null
python3 scripts/release_contract.py state-advance --state-file "${state_file}" \
  --release-id "${release_id}" --stage preflight >/dev/null
scripts/backup_release.sh --env-file "${ENV_FILE}" --state-file "${state_file}" --output-dir "${BACKUP_DIR}"
bundle="${BACKUP_DIR}/${release_id}.tar.gpg"
scripts/verify_restore.sh --env-file "${ENV_FILE}" --bundle "${bundle}" --passphrase-file "${passphrase_file}"

"${compose[@]}" stop api worker frontend >/dev/null
"${compose[@]}" up -d --no-build --wait --wait-timeout 120 api worker frontend >/dev/null
"${compose[@]}" exec -T api python -m app.operations.readiness --write-canary >/dev/null
release_log recovery_same_revision passed
release_log rehearsal passed
