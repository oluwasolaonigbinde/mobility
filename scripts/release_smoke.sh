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
EXPECTED_DATABASE_REVISION=""
EXPECT_EMPTY_USER_TABLE=false
TEMP_DIR=""

usage() {
  cat <<'EOF'
Usage: scripts/release_smoke.sh [--email ADDRESS (--password-file PATH | --password-stdin)]
       [--expected-database-revision REVISION] [--expect-empty-user-table]

Required environment:
  SMOKE_BASE_URL       Public edge URL, for example https://staging.invalid
  COMPOSE_ENV_FILE     Root-readable deployment environment file

The account must already exist. The smoke check performs no seed or business write.
On a first release only, --expect-empty-user-table proves there is no account to test.
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
    --expected-database-revision)
      [[ $# -ge 2 ]] || { echo "ERROR: --expected-database-revision requires a value" >&2; exit 2; }
      EXPECTED_DATABASE_REVISION="$2"
      shift
      ;;
    --expect-empty-user-table)
      EXPECT_EMPTY_USER_TABLE=true
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

[[ -n "${SMOKE_BASE_URL}" ]] || { echo "ERROR: SMOKE_BASE_URL is required" >&2; exit 2; }
[[ -n "${COMPOSE_ENV_FILE}" ]] || { echo "ERROR: COMPOSE_ENV_FILE is required" >&2; exit 2; }
[[ -r "${COMPOSE_ENV_FILE}" ]] || { echo "ERROR: COMPOSE_ENV_FILE is not readable" >&2; exit 2; }
if [[ "${EXPECT_EMPTY_USER_TABLE}" == true && ( -n "${EMAIL}" || -n "${PASSWORD_FILE}" \
  || "${READ_PASSWORD_STDIN}" == true ) ]]; then
  echo "ERROR: empty-user smoke cannot accept account credentials" >&2
  exit 2
fi
if [[ "${EXPECT_EMPTY_USER_TABLE}" != true && -z "${EMAIL}" ]]; then
  echo "ERROR: --email is required" >&2
  exit 2
fi
if [[ -n "${PASSWORD_FILE}" && "${READ_PASSWORD_STDIN}" == true ]]; then
  echo "ERROR: choose exactly one password input method" >&2
  exit 2
fi
if [[ "${EXPECT_EMPTY_USER_TABLE}" != true && -z "${PASSWORD_FILE}" \
  && "${READ_PASSWORD_STDIN}" == false ]]; then
  echo "ERROR: a password input method is required" >&2
  exit 2
fi

umask 077
TEMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/mobility-smoke.XXXXXX")"
readonly LOGIN_REQUEST="${TEMP_DIR}/login.json"

if [[ "${EXPECT_EMPTY_USER_TABLE}" == true ]]; then
  :
elif [[ "${READ_PASSWORD_STDIN}" == true ]]; then
  PASSWORD_FILE="${TEMP_DIR}/password"
  IFS= read -r password
  printf '%s' "${password}" >"${PASSWORD_FILE}"
  unset password
else
  [[ -f "${PASSWORD_FILE}" && -r "${PASSWORD_FILE}" ]] \
    || { echo "ERROR: password file is not a readable regular file" >&2; exit 2; }
  password_file_authority="$(python3 - "${PASSWORD_FILE}" "${REPO_ROOT}" <<'PY'
import os
import stat
import sys
from pathlib import Path

path = Path(sys.argv[1]).expanduser().resolve()
repository = Path(sys.argv[2]).resolve()
if not path.is_file() or not os.access(path, os.R_OK):
    raise SystemExit("ERROR: password file is not a readable regular file")
if path == repository or repository in path.parents:
    raise SystemExit("ERROR: password file must stay outside the repository")
if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
    raise SystemExit("ERROR: password file must have mode 0600 or stricter")
print(path)
PY
)"
  protected_password_file="${TEMP_DIR}/password"
  install -m 600 "${password_file_authority}" "${protected_password_file}"
  PASSWORD_FILE="${protected_password_file}"
fi

if [[ "${EXPECT_EMPTY_USER_TABLE}" != true ]]; then
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
fi

if [[ -n "${COMPOSE_BASE_FILE}" ]]; then
  compose=(docker compose -f "${COMPOSE_BASE_FILE}" -f "${COMPOSE_PRODUCTION_FILE}" --env-file "${COMPOSE_ENV_FILE}")
else
  compose=(docker compose -f "${COMPOSE_PRODUCTION_FILE}" --env-file "${COMPOSE_ENV_FILE}")
fi

echo "Checking public edge/frontend..."
curl_args=(--fail --silent --show-error --retry 5 --retry-all-errors --retry-delay 1)
if [[ "${RELEASE_LOCAL_REHEARSAL:-false}" == true ]]; then
  curl_args+=(--insecure)
fi
headers="$(curl "${curl_args[@]}" --head "${SMOKE_BASE_URL%/}/login")"
grep -Eiq '^strict-transport-security:.*max-age=31536000' <<<"${headers}" \
  || { echo "ERROR: public edge lacks the required HSTS policy" >&2; exit 1; }
curl "${curl_args[@]}" --output /dev/null "${SMOKE_BASE_URL%/}/health"

echo "Checking private API readiness..."
"${compose[@]}" exec -T api python -c \
  'from urllib.request import urlopen; r=urlopen("http://127.0.0.1:8000/api/v1/health/ready",timeout=5); raise SystemExit(0 if r.status == 200 else 1)' \
  >/dev/null

echo "Checking database migration revision..."
heads_output="$("${compose[@]}" exec -T api alembic heads)"
head_count="$(awk 'NF {count++} END {print count+0}' <<<"${heads_output}")"
code_head="$(awk 'NF {print $1}' <<<"${heads_output}")"
if [[ -n "${EXPECTED_DATABASE_REVISION}" ]]; then
  db_current="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
    'SELECT version_num FROM alembic_version')"
  current_count=1
  expected_revision="${EXPECTED_DATABASE_REVISION}"
else
  current_output="$("${compose[@]}" exec -T api alembic current)"
  current_count="$(awk 'NF {count++} END {print count+0}' <<<"${current_output}")"
  db_current="$(awk 'NF {print $1}' <<<"${current_output}")"
  expected_revision="${code_head}"
fi
if [[ "${head_count}" != 1 || "${current_count}" != 1 || -z "${code_head}" \
  || -z "${expected_revision}" || "${db_current}" != "${expected_revision}" ]]; then
  echo "ERROR: database revision does not match the expected forward migration revision" >&2
  exit 1
fi

echo "Checking authenticated Redis..."
redis_reply="$("${compose[@]}" exec -T redis sh -c \
  'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli --no-auth-warning ping')"
[[ "${redis_reply}" == "PONG" ]] \
  || { echo "ERROR: authenticated Redis PING failed" >&2; exit 1; }

echo "Checking mandatory worker heartbeat..."
"${compose[@]}" exec -T api arq --check app.jobs.worker_entry.WorkerSettings >/dev/null

if [[ "${EXPECT_EMPTY_USER_TABLE}" == true ]]; then
  echo "Checking first-release empty user authority..."
  user_count="$("${compose[@]}" exec -T db psql -U mobility -d mobility -Atc \
    'SELECT count(*) FROM users')"
  [[ "${user_count}" == "0" ]] \
    || { echo "ERROR: first-release smoke expected an empty user table" >&2; exit 1; }
  echo "First-release infrastructure smoke passed without inventing an account."
  exit 0
fi

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
