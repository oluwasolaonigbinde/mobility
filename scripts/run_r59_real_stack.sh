#!/usr/bin/env bash
set -Eeuo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

for executable in xvfb-run openbox xprop; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "R59 native visibility requires $executable" >&2
    exit 2
  fi
done

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
cookie_frontend="${R59_PROJECT}-cookie"
cookie_tls_dir=""
cookie_proxy_pid=""

cleanup() {
  local original_status=$?
  local down_status=0
  trap - EXIT INT TERM
  set +e
  cd "$repo_root"
  mkdir -p "$R59_ARTIFACT_DIR"
  "${compose[@]}" ps --all >"$R59_ARTIFACT_DIR/compose-ps.txt" 2>&1
  "${compose[@]}" logs --no-color api worker frontend >"$R59_ARTIFACT_DIR/stack.log" 2>&1
  if [[ -n "$cookie_proxy_pid" ]]; then
    kill "$cookie_proxy_pid" 2>/dev/null || true
    wait "$cookie_proxy_pid" 2>/dev/null || true
  fi
  # The one-off frontend belongs only to this newly created, validated project.
  if docker inspect "$cookie_frontend" >/dev/null 2>&1; then
    docker container rm -f "$cookie_frontend" || down_status=$?
  fi
  if [[ -n "$cookie_tls_dir" && "$cookie_tls_dir" == /tmp/cardvert-r59-tls.* ]]; then
    rm -rf -- "$cookie_tls_dir"
  fi
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
  "SELECT count(*) FROM campaign_assignments a JOIN driver_profiles d ON d.id=a.driver_profile_id JOIN users u ON u.id=d.user_id JOIN assignment_rule_bindings b ON b.assignment_id=a.id JOIN campaign_liability_reservations r ON r.assignment_id=a.id JOIN installation_evidence_submissions p ON p.assignment_id=a.id WHERE u.email='driver@demo.mobility.local' AND a.status='active' AND b.campaign_window_start_at <= now() AND b.campaign_window_end_at > now() AND r.status='reserved' AND p.status='approved' AND p.approved_until > now();")"
if [[ "$preflight_count" != "1" ]]; then
  echo "R59 readiness preflight failed closed" >&2
  exit 1
fi

export R59_IMAGE_IDS="$("${compose[@]}" images -q api worker frontend | sort -u | paste -sd, -)"
leased_paths=(
  .github/workflows/ci.yml
  frontend/playwright.config.ts
  frontend/e2e/r59-real-stack.spec.ts
  frontend/e2e/security-boundary.spec.ts
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
export PLAYWRIGHT_JSON_OUTPUT_FILE="$R59_ARTIFACT_DIR/r59-playwright.json"
# Use a new X display and its own window manager: native minimize/restore must
# reach X11 rather than an emulated visibility property or a shared desktop.
xvfb-run -a bash -c '
  set -Eeuo pipefail
  openbox --sm-disable >"$R59_ARTIFACT_DIR/window-manager.log" 2>&1 &
  wm_pid=$!
  trap '\''status=$?; trap - EXIT INT TERM; kill "$wm_pid" 2>/dev/null || true; wait "$wm_pid" 2>/dev/null || true; exit "$status"'\'' EXIT
  trap '\''exit 130'\'' INT
  trap '\''exit 143'\'' TERM
  wm_ready=0
  for attempt in $(seq 1 50); do
    if ! kill -0 "$wm_pid" 2>/dev/null; then
      echo "R59 window manager exited before readiness" >&2
      exit 1
    fi
    if xprop -root _NET_SUPPORTING_WM_CHECK | grep -Eq "window id # 0x[1-9a-f][0-9a-f]*"; then
      wm_ready=1
      break
    fi
    sleep 0.1
  done
  if (( wm_ready != 1 )); then
    echo "R59 native window manager did not become ready" >&2
    exit 1
  fi
  npx playwright test e2e/r59-real-stack.spec.ts --project=r59-chromium --workers=1 --retries=0 --reporter=list,json
'

# Reuse this exact candidate's production image for the real HTTPS logout
# boundary, including an actual API outage. No additional CI job or build.
cd "$repo_root"
export R14_SECURITY_LOGIN_EMAIL="admin@demo.mobility.local"
export R14_SECURITY_LOGIN_PASSWORD="DemoAdmin12345!"
export E2E_API_BASE_URL="http://127.0.0.1:${R59_API_PORT}"
: "${R14_SECURITY_LOGIN_EMAIL:?synthetic cookie login email required}"
: "${R14_SECURITY_LOGIN_PASSWORD:?synthetic cookie login password required}"
: "${E2E_API_BASE_URL:?isolated cookie backend required}"
export R59_COOKIE_REVOCATION_OUTAGE=1
export R14_SECURITY_BOUNDARY=1
unset R59_REAL_STACK
cookie_http_port=34160
cookie_https_port=34161
cookie_image="${R59_PROJECT}-frontend:${R59_GIT_SHA}"
cookie_image_id="$(docker image inspect --format '{{.Id}}' "$cookie_image")"
"${compose[@]}" run -d --no-deps --name "$cookie_frontend" \
  --publish "127.0.0.1:${cookie_http_port}:3000" \
  -e SESSION_COOKIE_NAME=__Host-cardvert_session frontend >/dev/null
if [[ "$(docker inspect --format '{{.Image}}' "$cookie_frontend")" != "$cookie_image_id" ]]; then
  echo "HTTPS frontend did not reuse the exact candidate image" >&2
  exit 1
fi
wait_for_url "http://127.0.0.1:${cookie_http_port}/login" cookie-frontend
cookie_tls_dir="$(mktemp -d /tmp/cardvert-r59-tls.XXXXXX)"
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=localhost \
  -addext subjectAltName=DNS:localhost \
  -keyout "$cookie_tls_dir/key.pem" -out "$cookie_tls_dir/cert.pem" >/dev/null 2>&1
cat >"$cookie_tls_dir/proxy.cjs" <<'JS'
const fs = require('node:fs');
const http = require('node:http');
const https = require('node:https');
const [directory, upstreamPort, tlsPort] = process.argv.slice(2);
https.createServer({key: fs.readFileSync(`${directory}/key.pem`), cert: fs.readFileSync(`${directory}/cert.pem`)}, (request, response) => {
  const upstream = http.request({hostname: '127.0.0.1', port: Number(upstreamPort), method: request.method, path: request.url, headers: {...request.headers, 'x-forwarded-proto': 'https', 'x-forwarded-host': request.headers.host}}, (result) => {
    response.writeHead(result.statusCode, result.headers);
    result.pipe(response);
  });
  upstream.on('error', () => {response.writeHead(502); response.end('Isolated frontend unavailable');});
  request.pipe(upstream);
}).listen(Number(tlsPort), '127.0.0.1');
JS
node "$cookie_tls_dir/proxy.cjs" "$cookie_tls_dir" "$cookie_http_port" "$cookie_https_port" &
cookie_proxy_pid=$!
export PLAYWRIGHT_BASE_URL="https://localhost:${cookie_https_port}"
export PLAYWRIGHT_IGNORE_HTTPS_ERRORS=1
# Trust only this disposable loopback certificate for the bootstrap health read.
for attempt in $(seq 1 30); do
  if curl --fail --silent --cacert "$cookie_tls_dir/cert.pem" "$PLAYWRIGHT_BASE_URL/login" >/dev/null; then break; fi
  if [[ "$attempt" == 30 ]]; then echo "HTTPS cookie frontend unavailable" >&2; exit 1; fi
  sleep 1
done
cd frontend
PLAYWRIGHT_JSON_OUTPUT_FILE="$cookie_tls_dir/result.json" npx playwright test \
  e2e/security-boundary.spec.ts --project=chromium --workers=1 --retries=0 \
  --grep 'production login and sign-out set and expire the host-only hardened session cookie$' \
  --reporter=list,json --output=test-results/r59-real-stack/cookie-playwright
node - "$cookie_tls_dir/result.json" "$R59_ARTIFACT_DIR/HTTPS_LOGOUT_RECEIPT.json" "$R59_GIT_SHA" "$cookie_image_id" "$R59_ARTIFACT_DIR/r59-playwright.json" <<'JS'
const fs = require('node:fs');
const [reportPath, receiptPath, candidate, image, r59Path] = process.argv.slice(2);
const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
const specs = [];
function visit(suite) { specs.push(...(suite.specs || [])); for (const child of suite.suites || []) visit(child); }
for (const suite of report.suites || []) visit(suite);
const title = 'production login and sign-out set and expire the host-only hardened session cookie';
const test = specs[0]?.tests?.[0];
if (specs.length !== 1 || specs[0].title !== title || specs[0].tests.length !== 1 || test.projectName !== 'chromium' || test.results.length !== 1 || test.results[0].status !== 'passed' || report.stats.expected !== 1 || report.stats.skipped !== 0 || report.stats.unexpected !== 0) throw new Error('HTTPS logout requires exactly one executed, passed Chromium case without retries or skips');
specs.length = 0;
const r59 = JSON.parse(fs.readFileSync(r59Path, 'utf8'));
for (const suite of r59.suites || []) visit(suite);
if (specs.length !== 2 || r59.stats.expected !== 2 || r59.stats.skipped !== 0 || r59.stats.unexpected !== 0 || specs.some(spec => spec.tests.length !== 1 || spec.tests[0].projectName !== 'r59-chromium' || spec.tests[0].results.length !== 1 || spec.tests[0].results[0].status !== 'passed')) throw new Error('R59 requires both original and recovery browser cases to execute and pass without skips or retries');
const expectedR59 = ['R59 real-stack release journey survives outages and converges exactly once', 'R59 uncertain Start preserves offline evidence across bounded cache releases'];
if (specs.some(spec => !expectedR59.includes(spec.title)) || new Set(specs.map(spec => spec.title)).size !== 2) throw new Error('R59 executed cases differ from the approved original and recovery journeys');
fs.writeFileSync(receiptPath, JSON.stringify({candidate, image, case: title, project: 'chromium', executed: 1, passed: 1, skipped: 0, retries: 0, realApiOutageRequired: process.env.R59_COOKIE_REVOCATION_OUTAGE === '1', r59Cases: specs.map(spec => spec.title), r59Executed: 2, r59Passed: 2}, null, 2));
JS
