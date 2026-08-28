#!/usr/bin/env bash

set -Eeuo pipefail

readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly COMPOSE_BASE_FILE="${COMPOSE_BASE_FILE:-}"
readonly COMPOSE_PRODUCTION_FILE="${COMPOSE_PRODUCTION_FILE:-${REPO_ROOT}/docker-compose.production.yml}"
readonly COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-}"
readonly SMOKE_BASE_URL="${SMOKE_BASE_URL:-}"

EMAIL=""
PASSWORD_FILE=""
READ_PASSWORD_STDIN=false
TEMP_DIR=""

usage() {
  cat <<'EOF'
Usage: scripts/release_smoke.sh --email ADDRESS (--password-file PATH | --password-stdin)

Required environment:
  SMOKE_BASE_URL       Public edge URL, for example https://staging.invalid
  COMPOSE_ENV_FILE     Root-readable deployment environment file

The account must already exist. The smoke check performs no seed or business write.
EOF
}

cleanup() {
  if [[ -n "${TEMP_DIR}" && -d "${TEMP_DIR}" ]]; then
    rm -rf "${TEMP_DIR}"
  fi
}
trap cleanup EXIT HUP INT TERM

while (( $# > 0 )); do
  case "$1" in
    --email)
      [[ $# -ge 2 ]] || { echo "ERROR: --email requires a value" >&2; exit 2; }
      EMAIL="$2"
      shift
      ;;
    --password-file)
      [[ $# -ge 2 ]] || { echo "ERROR: --password-file requires a path" >&2; exit 2; }
      PASSWORD_FILE="$2"
      shift
      ;;
    --password-stdin)
      READ_PASSWORD_STDIN=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

[[ -n "${EMAIL}" ]] || { echo "ERROR: --email is required" >&2; exit 2; }
[[ -n "${SMOKE_BASE_URL}" ]] || { echo "ERROR: SMOKE_BASE_URL is required" >&2; exit 2; }
[[ -n "${COMPOSE_ENV_FILE}" ]] || { echo "ERROR: COMPOSE_ENV_FILE is required" >&2; exit 2; }
[[ -r "${COMPOSE_ENV_FILE}" ]] || { echo "ERROR: COMPOSE_ENV_FILE is not readable" >&2; exit 2; }
if [[ -n "${PASSWORD_FILE}" && "${READ_PASSWORD_STDIN}" == true ]]; then
  echo "ERROR: choose exactly one password input method" >&2
  exit 2
fi
if [[ -z "${PASSWORD_FILE}" && "${READ_PASSWORD_STDIN}" == false ]]; then
  echo "ERROR: a password input method is required" >&2
  exit 2
fi

umask 077
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mobility-smoke.XXXXXX")"
readonly LOGIN_REQUEST="${TEMP_DIR}/login.json"

if [[ "${READ_PASSWORD_STDIN}" == true ]]; then
  PASSWORD_FILE="${TEMP_DIR}/password"
  IFS= read -r password
  printf '%s' "${password}" >"${PASSWORD_FILE}"
  unset password
else
  [[ -f "${PASSWORD_FILE}" && -r "${PASSWORD_FILE}" ]] \
    || { echo "ERROR: password file is not a readable regular file" >&2; exit 2; }
  protected_password_file="${TEMP_DIR}/password"
  install -m 600 "${PASSWORD_FILE}" "${protected_password_file}"
  PASSWORD_FILE="${protected_password_file}"
fi

python3 - "${EMAIL}" "${PASSWORD_FILE}" "${LOGIN_REQUEST}" <<'PY'
import json
import os
import sys

email, password_path, output_path = sys.argv[1:]
with open(password_path, encoding="utf-8") as source:
    password = source.read().rstrip("\r\n")
if not password:
    raise SystemExit("ERROR: password is empty")
descriptor = os.open(output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, "w", encoding="utf-8") as output:
    json.dump({"email": email, "password": password}, output)
PY

if [[ -n "${COMPOSE_BASE_FILE}" ]]; then
  compose=(docker compose -f "${COMPOSE_BASE_FILE}" -f "${COMPOSE_PRODUCTION_FILE}" --env-file "${COMPOSE_ENV_FILE}")
else
  compose=(docker compose -f "${COMPOSE_PRODUCTION_FILE}" --env-file "${COMPOSE_ENV_FILE}")
fi

echo "Checking public edge/frontend..."
headers="$(curl --fail --silent --show-error --head "${SMOKE_BASE_URL%/}/login")"
grep -Eiq '^strict-transport-security:.*max-age=31536000' <<<"${headers}" \
  || { echo "ERROR: public edge lacks the required HSTS policy" >&2; exit 1; }
curl --fail --silent --show-error --output /dev/null "${SMOKE_BASE_URL%/}/health"

echo "Checking private API readiness..."
"${compose[@]}" exec -T api python -c \
  'from urllib.request import urlopen; r=urlopen("http://127.0.0.1:8000/api/v1/health/ready",timeout=5); raise SystemExit(0 if r.status == 200 else 1)' \
  >/dev/null

echo "Checking database migration revision..."
heads_output="$("${compose[@]}" exec -T api alembic heads)"
current_output="$("${compose[@]}" exec -T api alembic current)"
head_count="$(awk 'NF {count++} END {print count+0}' <<<"${heads_output}")"
current_count="$(awk 'NF {count++} END {print count+0}' <<<"${current_output}")"
code_head="$(awk 'NF {print $1}' <<<"${heads_output}")"
db_current="$(awk 'NF {print $1}' <<<"${current_output}")"
if [[ "${head_count}" != 1 || "${current_count}" != 1 || -z "${code_head}" || "${db_current}" != "${code_head}" ]]; then
  echo "ERROR: database revision does not match checked-out Alembic head" >&2
  exit 1
fi

echo "Checking authenticated Redis..."
redis_reply="$("${compose[@]}" exec -T redis sh -c \
  'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --no-auth-warning ping')"
[[ "${redis_reply}" == "PONG" ]] \
  || { echo "ERROR: authenticated Redis PING failed" >&2; exit 1; }

echo "Checking mandatory worker heartbeat..."
"${compose[@]}" exec -T api arq --check app.jobs.worker_entry.WorkerSettings >/dev/null

echo "Checking login with the supplied pre-existing account..."
"${compose[@]}" exec -T api python -c '
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen
request = Request(
    "http://127.0.0.1:8000/api/v1/auth/login",
    data=sys.stdin.buffer.read(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
try:
    response = urlopen(request, timeout=10)
except HTTPError as error:
    print(f"ERROR: login failed with HTTP {error.code}", file=sys.stderr)
    raise SystemExit(1)
if response.status != 200:
    print(f"ERROR: login failed with HTTP {response.status}", file=sys.stderr)
    raise SystemExit(1)
response.close()
' <"${LOGIN_REQUEST}"

echo "Release smoke passed."
