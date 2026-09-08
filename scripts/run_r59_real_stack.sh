#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

export R59_PROJECT="${R59_PROJECT:-cardvert-r59-${GITHUB_RUN_ID:-local}-$(date +%s)-$$}"
if [[ ! "$R59_PROJECT" =~ ^cardvert-r59-[a-z0-9-]+$ ]]; then
  echo "R59 project must match ^cardvert-r59-[a-z0-9-]+$" >&2
  exit 2
fi
if docker compose ls --all --format json | grep -Eq "\"Name\"[[:space:]]*:[[:space:]]*\"${R59_PROJECT}\""; then
  echo "R59 refuses to reuse existing Compose project $R59_PROJECT" >&2
  exit 2
fi

export R59_GIT_SHA="$(git rev-parse HEAD)"
export R59_API_PORT="${R59_API_PORT:-48159}"
export R59_FRONTEND_PORT="${R59_FRONTEND_PORT:-34159}"
export PAYOUT_CRYPTO_KEYRING_B64='{"1":"AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="}'
export R59_ARTIFACT_DIR="$repo_root/frontend/test-results/r59-real-stack"
mkdir -p "$R59_ARTIFACT_DIR"

compose=(docker compose -p "$R59_PROJECT" --profile full -f docker-compose.yml -f frontend/e2e/support/docker-compose.r59.yml)

cleanup() {
  local original_status=$?
  local down_status=0
  trap - EXIT INT TERM
  set +e
  cd "$repo_root"
  mkdir -p "$R59_ARTIFACT_DIR"
  "${compose[@]}" ps --all >"$R59_ARTIFACT_DIR/compose-ps.txt" 2>&1
  "${compose[@]}" logs --no-color api worker frontend >"$R59_ARTIFACT_DIR/stack.log" 2>&1
  "${compose[@]}" down -v --remove-orphans || down_status=$?
  if (( original_status == 0 && down_status != 0 )); then
    echo "R59 exact-project teardown failed" >&2
    exit "$down_status"
  fi
  exit "$original_status"
}
trap cleanup EXIT INT TERM

wait_for_postgres() {
  for attempt in $(seq 1 60); do
    if "${compose[@]}" exec -T db pg_isready -h 127.0.0.1 -U mobility -d mobility >/dev/null; then
      return 0
    fi
    if [[ "$attempt" == "60" ]]; then
      echo "PostGIS did not become ready" >&2
      return 1
    fi
    sleep 2
  done
}

wait_for_url() {
  local url=$1
  local label=$2
  for attempt in $(seq 1 90); do
    if curl --fail --silent --show-error "$url" >/dev/null; then
      return 0
    fi
    if [[ "$attempt" == "90" ]]; then
      echo "$label did not become ready" >&2
      return 1
    fi
    sleep 2
  done
}

wait_for_local_dependencies() {
  for attempt in $(seq 1 90); do
    if "${compose[@]}" exec -T api python - <<'PY' >/dev/null 2>&1
import socket
from urllib.request import urlopen

for host, port in (("redis", 6379), ("clamav", 3310), ("mailpit", 1025)):
    with socket.create_connection((host, port), timeout=2):
        pass
with urlopen("http://minio:9000/minio/health/live", timeout=2) as response:
    if response.status != 200:
        raise RuntimeError("MinIO health check failed")
PY
    then
      return 0
    fi
    if [[ "$attempt" == "90" ]]; then
      echo "Redis, MinIO, ClamAV, or Mailpit did not become ready" >&2
      return 1
    fi
    sleep 2
  done
}

services=(db redis minio minio-init clamav mailpit api frontend)
if [[ "${R59_WITHHOLD_WORKER:-0}" != "1" ]]; then
  services+=(worker)
fi
"${compose[@]}" up -d --build "${services[@]}"
wait_for_postgres
wait_for_url "http://127.0.0.1:${R59_API_PORT}/health" API
wait_for_local_dependencies
"${compose[@]}" exec -T api alembic upgrade head
"${compose[@]}" exec -T api python -m app.seeds.demo

# The ordinary seed now supplies local Start authority; the following check
# verifies that result without an R59-only repair.

preflight_count="$("${compose[@]}" exec -T db psql -XAt -v ON_ERROR_STOP=1 -U mobility -d mobility -c \
  "SELECT count(*) FROM campaign_assignments a JOIN driver_profiles d ON d.id=a.driver_profile_id JOIN users u ON u.id=d.user_id JOIN assignment_rule_bindings b ON b.assignment_id=a.id JOIN campaign_liability_reservations r ON r.assignment_id=a.id JOIN display_proofs p ON p.assignment_id=a.id WHERE u.email='driver@demo.mobility.local' AND a.status='active' AND r.status='reserved' AND p.valid_until > now();")"
if [[ "$preflight_count" != "1" ]]; then
  echo "R59 readiness preflight failed closed" >&2
  exit 1
fi

export R59_IMAGE_IDS="$("${compose[@]}" images -q api worker frontend | sort -u | paste -sd, -)"
leased_paths=(
  .github/workflows/ci.yml
  frontend/playwright.config.ts
  frontend/e2e/r59-real-stack.spec.ts
  frontend/e2e/support/r59-stack.ts
  frontend/e2e/support/docker-compose.r59.yml
  scripts/run_r59_real_stack.sh
  tests/test_r59_real_stack_contract.py
  docs/pkg-07-w4-01d-release-rehearsal.md
)
export R59_LEASED_FILES_DIGEST="$(git hash-object "${leased_paths[@]}" | git hash-object --stdin)"
export R59_REAL_STACK=1
export PLAYWRIGHT_BASE_URL="http://127.0.0.1:${R59_FRONTEND_PORT}"

wait_for_url "$PLAYWRIGHT_BASE_URL/login" frontend
cd frontend
if command -v xvfb-run >/dev/null 2>&1; then
  xvfb-run -a npx playwright test e2e/r59-real-stack.spec.ts --project=r59-chromium --workers=1 --retries=0
else
  npx playwright test e2e/r59-real-stack.spec.ts --project=r59-chromium --workers=1 --retries=0
fi
