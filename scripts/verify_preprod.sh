#!/usr/bin/env bash

set -Eeuo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ENV_FILE="${REPO_ROOT}/production.env.example"
readonly PROD_FILE="${REPO_ROOT}/docker-compose.production.yml"
readonly DEV_FILE="${REPO_ROOT}/docker-compose.yml"

run_tests=true
if [[ "${1:-}" == "--static-only" ]]; then
  run_tests=false
  shift
fi
if (( $# != 0 )); then
  echo "usage: $0 [--static-only]" >&2
  exit 2
fi

cd "${REPO_ROOT}"

bash -n scripts/db_backup.sh scripts/db_restore.sh scripts/release_smoke.sh scripts/verify_preprod.sh \
  scripts/release_common.sh scripts/release.sh scripts/recover_release.sh \
  scripts/backup_release.sh scripts/verify_restore.sh scripts/rehearse_w403a.sh
docker compose -f "${DEV_FILE}" --env-file "${REPO_ROOT}/.env.example" config --format json >/dev/null
# Templates keep secrets blank; these stand-ins are scoped to rendering only.
POSTGRES_PASSWORD=synthetic-render-password \
REDIS_PASSWORD=synthetic-render-password \
DATABASE_URL='postgresql+asyncpg://mobility:synthetic@db/mobility?ssl=verify-full' \
REDIS_URL='rediss://:synthetic@redis:6379/0?ssl_cert_reqs=required' \
JWT_SECRET_KEY=synthetic-render-secret-at-least-32-characters \
PAYOUT_CRYPTO_KEYRING_B64='{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}' \
TRIP_EVIDENCE_SIGNING_KEYRING_B64='{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}' \
OBJECT_STORAGE_ACCESS_KEY_ID=synthetic-render-key \
OBJECT_STORAGE_SECRET_ACCESS_KEY=synthetic-render-secret \
docker compose -f "${PROD_FILE}" --profile release --env-file "${ENV_FILE}" config --format json \
  | python3 -m json.tool >/dev/null
docker run --rm \
  -e EDGE_HOSTNAME=http://localhost \
  -e RELEASE_REVISION=1715fe53b19972cd6db829a08a9d6cf572fbd656 \
  -v "${REPO_ROOT}/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy@sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17 \
  caddy validate --config /etc/caddy/Caddyfile
if [[ "${run_tests}" == "true" ]]; then
  pytest -q tests/test_preprod_operations.py tests/test_w403a_release_preparation.py
fi
