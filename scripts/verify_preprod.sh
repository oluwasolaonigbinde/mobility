#!/usr/bin/env bash

set -Eeuo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ENV_FILE="${REPO_ROOT}/staging.env.example"
readonly PROD_FILE="${REPO_ROOT}/docker-compose.production.yml"
readonly DEV_FILE="${REPO_ROOT}/docker-compose.yml"

cd "${REPO_ROOT}"

bash -n scripts/db_backup.sh scripts/db_restore.sh scripts/release_smoke.sh scripts/verify_preprod.sh
docker compose -f docker-compose.yml config --format json >/dev/null
docker compose -f "${DEV_FILE}" -f "${PROD_FILE}" --env-file "${ENV_FILE}" config --format json \
  | python3 -m json.tool >/dev/null
docker run --rm \
  -e EDGE_HOSTNAME=http://localhost \
  -v "${REPO_ROOT}/Caddyfile:/etc/caddy/Caddyfile:ro" \
  caddy:2.8-alpine caddy validate --config /etc/caddy/Caddyfile
pytest -q tests/test_preprod_operations.py
