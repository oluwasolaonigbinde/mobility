#!/usr/bin/env bash

set -Eeuo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ENV_FILE="${REPO_ROOT}/production.env.example"
readonly PROD_FILE="${REPO_ROOT}/docker-compose.production.yml"
readonly DEV_FILE="${REPO_ROOT}/docker-compose.yml"

cd "${REPO_ROOT}"

bash -n scripts/db_backup.sh scripts/db_restore.sh scripts/release_smoke.sh scripts/verify_preprod.sh \
  scripts/release_common.sh scripts/release.sh scripts/recover_release.sh \
  scripts/backup_release.sh scripts/verify_restore.sh scripts/rehearse_w403a.sh
docker compose -f "${DEV_FILE}" --env-file "${REPO_ROOT}/.env.example" config --format json >/dev/null
docker compose -f "${PROD_FILE}" --profile release --env-file "${ENV_FILE}" config --format json \
  | python3 -m json.tool >/dev/null
docker run --rm \
  -e EDGE_HOSTNAME=http://localhost \
  -e RELEASE_REVISION=1715fe53b19972cd6db829a08a9d6cf572fbd656 \
  -v "${REPO_ROOT}/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy@sha256:af32e97399febea808609119bb21544d0265c58a02836576e32a2d082c262c17 \
  caddy validate --config /etc/caddy/Caddyfile
pytest -q tests/test_preprod_operations.py tests/test_w403a_release_preparation.py
