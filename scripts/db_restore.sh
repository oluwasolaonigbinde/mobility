#!/usr/bin/env bash

set -Eeuo pipefail

readonly DB_SERVICE="db"
readonly API_SERVICE="api"
readonly FRONTEND_SERVICE="frontend"
readonly DB_NAME="mobility"
readonly DB_USER="mobility"
readonly TEMP_DB="mobility_restore_tmp"
readonly REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Lowercase: these become unquoted SQL identifiers in ALTER DATABASE, and
# Postgres folds unquoted identifiers to lowercase — an uppercase name here
# would make the printed dropdb/recovery commands reference a database that
# does not exist.
readonly UTC_TIMESTAMP="$(date -u +%Y%m%dt%H%M%Sz)"
readonly SAFETY_DB="mobility_pre_restore_${UTC_TIMESTAMP}"
readonly FAILED_DB="mobility_failed_restore_${UTC_TIMESTAMP}"

STAGE="arguments"
RESTORE_ERROR_DETAIL="command failed"
UPGRADE=false
DUMP_FILE=""
APP_STOPPED=0
FRONTEND_WAS_RUNNING=0
LIVE_RENAMED=0
TEMP_RENAMED=0
TEMP_CREATED=0

usage() {
  cat <<'EOF'
Usage: scripts/db_restore.sh [--upgrade] <dumpfile>

Restores a pg_dump custom-format backup into a temporary database, validates
its Alembic revision, then swaps it into place. Use --upgrade only when the
dump is at a known revision older than the checked-out code head.
EOF
}

compose_ps_running() {
  docker compose --profile full ps --status running --services 2>/dev/null \
    | grep -qx "$1"
}

start_app_surface() {
  docker compose up -d "${API_SERVICE}" >/dev/null
  if (( FRONTEND_WAS_RUNNING == 1 )); then
    docker compose --profile full up -d "${FRONTEND_SERVICE}" >/dev/null
  fi
}

drop_temp_database() {
  docker compose exec -T "${DB_SERVICE}" psql \
    --username="${DB_USER}" --dbname=postgres --set=ON_ERROR_STOP=1 \
    --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${TEMP_DB}' AND pid <> pg_backend_pid();" \
    >/dev/null 2>&1 || true
  docker compose exec -T "${DB_SERVICE}" dropdb \
    --username="${DB_USER}" --if-exists "${TEMP_DB}" >/dev/null 2>&1 || true
}

rollback_swap() {
  docker compose --profile full stop "${API_SERVICE}" "${FRONTEND_SERVICE}" \
    >/dev/null 2>&1 || true
  docker compose exec -T "${DB_SERVICE}" psql \
    --username="${DB_USER}" --dbname=postgres --set=ON_ERROR_STOP=1 \
    --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname IN ('${DB_NAME}', '${SAFETY_DB}') AND pid <> pg_backend_pid();" \
    >/dev/null 2>&1 || true

  if (( TEMP_RENAMED == 1 )); then
    docker compose exec -T "${DB_SERVICE}" psql \
      --username="${DB_USER}" --dbname=postgres --set=ON_ERROR_STOP=1 \
      --command="ALTER DATABASE ${DB_NAME} RENAME TO ${FAILED_DB}; ALTER DATABASE ${SAFETY_DB} RENAME TO ${DB_NAME};" \
      >/dev/null 2>&1
  elif (( LIVE_RENAMED == 1 )); then
    docker compose exec -T "${DB_SERVICE}" psql \
      --username="${DB_USER}" --dbname=postgres --set=ON_ERROR_STOP=1 \
      --command="ALTER DATABASE ${SAFETY_DB} RENAME TO ${DB_NAME};" \
      >/dev/null 2>&1
  fi
}

on_error() {
  local exit_code="$1"
  local line_number="$2"

  trap - ERR
  set +e

  echo >&2
  echo "restore FAILED at stage ${STAGE} — ${RESTORE_ERROR_DETAIL}" >&2
  echo "Failed command line: ${line_number}; exit code: ${exit_code}" >&2

  if (( TEMP_RENAMED == 1 || LIVE_RENAMED == 1 )); then
    if rollback_swap; then
      if (( TEMP_RENAMED == 1 )); then
        echo "Recovery complete: original database restored as ${DB_NAME}." >&2
        echo "Failed restored database retained as ${FAILED_DB}; inspect it, then prune with:" >&2
        echo "  docker compose exec -T db dropdb -U mobility ${FAILED_DB}" >&2
      else
        echo "Recovery complete: first rename was reversed; original database is ${DB_NAME}." >&2
        drop_temp_database
      fi
    else
      echo "AUTOMATIC RECOVERY FAILED. Keep the application stopped." >&2
      if (( TEMP_RENAMED == 1 )); then
        echo "Run: ALTER DATABASE ${DB_NAME} RENAME TO ${FAILED_DB}; ALTER DATABASE ${SAFETY_DB} RENAME TO ${DB_NAME};" >&2
      else
        echo "Run: ALTER DATABASE ${SAFETY_DB} RENAME TO ${DB_NAME};" >&2
      fi
      echo "Execute the SQL from a psql session connected to database postgres." >&2
      exit "${exit_code}"
    fi
  else
    if (( TEMP_CREATED == 1 )); then
      drop_temp_database
    fi
    if [[ "${STAGE}" == "arguments" || "${STAGE}" == "pre-validate" || "${STAGE}" == "confirmation" || "${STAGE}" == "capture-code-head" ]]; then
      echo "Recovery: live database and application were not touched." >&2
    else
      echo "Recovery: temporary database removed; live database untouched." >&2
    fi
  fi

  if (( APP_STOPPED == 1 )); then
    start_app_surface || echo "Application restart failed; run: docker compose up -d api" >&2
  fi
  exit "${exit_code}"
}
trap 'on_error $? $LINENO' ERR

while (( $# > 0 )); do
  case "$1" in
    --upgrade)
      UPGRADE=true
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    -*)
      usage >&2
      RESTORE_ERROR_DETAIL="unknown option: $1"
      false
      ;;
    *)
      if [[ -n "${DUMP_FILE}" ]]; then
        usage >&2
        RESTORE_ERROR_DETAIL="only one dump file may be supplied"
        false
      fi
      DUMP_FILE="$1"
      ;;
  esac
  shift
done

if [[ -z "${DUMP_FILE}" ]]; then
  usage >&2
  RESTORE_ERROR_DETAIL="dump file is required"
  false
fi
if [[ ! -r "${DUMP_FILE}" || ! -f "${DUMP_FILE}" ]]; then
  RESTORE_ERROR_DETAIL="dump file is not a readable regular file: ${DUMP_FILE}"
  false
fi
DUMP_FILE="$(cd "$(dirname "${DUMP_FILE}")" && pwd)/$(basename "${DUMP_FILE}")"

cd "${REPO_ROOT}"

STAGE="pre-validate"
RESTORE_ERROR_DETAIL="dump failed pg_restore --list; stack still running and live database untouched"
docker compose exec -T "${DB_SERVICE}" pg_restore --list <"${DUMP_FILE}" >/dev/null
echo "Pre-validation passed: ${DUMP_FILE}"

STAGE="confirmation"
echo "WARNING: this will replace database '${DB_NAME}' after validating a temporary restore."
printf "Type RESTORE to continue: "
read -r confirmation
if [[ "${confirmation}" != "RESTORE" ]]; then
  echo "Restore cancelled; stack and live database were not touched."
  exit 0
fi

STAGE="capture-code-head"
RESTORE_ERROR_DETAIL="could not read Alembic revisions from the API image"
ALEMBIC_SCRIPT='from alembic.config import Config; from alembic.script import ScriptDirectory; script=ScriptDirectory.from_config(Config("alembic.ini")); print(script.get_current_head()); [print(r.revision) for r in script.walk_revisions()]'
if compose_ps_running "${API_SERVICE}"; then
  ALEMBIC_INFO="$(docker compose exec -T "${API_SERVICE}" python -c "${ALEMBIC_SCRIPT}")"
else
  ALEMBIC_INFO="$(docker compose run --rm -T --no-deps "${API_SERVICE}" python -c "${ALEMBIC_SCRIPT}")"
fi
CODE_HEAD="$(printf '%s\n' "${ALEMBIC_INFO}" | sed -n '1p')"
KNOWN_REVISIONS="$(printf '%s\n' "${ALEMBIC_INFO}" | sed '1d')"
if [[ -z "${CODE_HEAD}" || -z "${KNOWN_REVISIONS}" ]]; then
  RESTORE_ERROR_DETAIL="Alembic reported no code head or revision list"
  false
fi
echo "Checked-out Alembic head: ${CODE_HEAD}"

if compose_ps_running "${FRONTEND_SERVICE}"; then
  FRONTEND_WAS_RUNNING=1
fi

STAGE="stop-writers"
RESTORE_ERROR_DETAIL="could not stop API/frontend writers"
APP_STOPPED=1
docker compose --profile full stop "${API_SERVICE}" "${FRONTEND_SERVICE}"

STAGE="prepare-temp"
RESTORE_ERROR_DETAIL="could not prepare temporary database; live database untouched"
drop_temp_database
docker compose exec -T "${DB_SERVICE}" createdb \
  --username="${DB_USER}" "${TEMP_DB}"
TEMP_CREATED=1

STAGE="restore-temp"
RESTORE_ERROR_DETAIL="temporary restore failed; live database untouched"
docker compose exec -T "${DB_SERVICE}" pg_restore \
  --username="${DB_USER}" --dbname="${TEMP_DB}" --no-owner --exit-on-error \
  <"${DUMP_FILE}"

STAGE="validate-revision"
RESTORE_ERROR_DETAIL="temporary database has no readable Alembic revision; live database untouched"
TEMP_REVISION="$(docker compose exec -T "${DB_SERVICE}" psql \
  --username="${DB_USER}" --dbname="${TEMP_DB}" --tuples-only --no-align \
  --set=ON_ERROR_STOP=1 --command='SELECT version_num FROM alembic_version;')"
TEMP_REVISION="$(printf '%s' "${TEMP_REVISION}" | tr -d '[:space:]')"
if [[ -z "${TEMP_REVISION}" ]]; then
  RESTORE_ERROR_DETAIL="temporary database Alembic revision is empty; live database untouched"
  false
fi
if ! grep -Fxq "${TEMP_REVISION}" <<<"${KNOWN_REVISIONS}"; then
  RESTORE_ERROR_DETAIL="dump revision ${TEMP_REVISION} is unknown to checked-out code (head ${CODE_HEAD}); live database untouched"
  false
fi
if [[ "${TEMP_REVISION}" != "${CODE_HEAD}" && "${UPGRADE}" != true ]]; then
  RESTORE_ERROR_DETAIL="dump revision ${TEMP_REVISION} is older than code head ${CODE_HEAD}; rerun with --upgrade after reviewing migrations"
  false
fi
echo "Temporary database revision validated: ${TEMP_REVISION}"

STAGE="swap-terminate-connections"
RESTORE_ERROR_DETAIL="could not terminate remaining live database connections"
docker compose exec -T "${DB_SERVICE}" psql \
  --username="${DB_USER}" --dbname=postgres --set=ON_ERROR_STOP=1 \
  --command="SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '${DB_NAME}' AND pid <> pg_backend_pid();" \
  >/dev/null

STAGE="swap-live-to-safety"
RESTORE_ERROR_DETAIL="could not rename live database to ${SAFETY_DB}"
docker compose exec -T "${DB_SERVICE}" psql \
  --username="${DB_USER}" --dbname=postgres --set=ON_ERROR_STOP=1 \
  --command="ALTER DATABASE ${DB_NAME} RENAME TO ${SAFETY_DB};"
LIVE_RENAMED=1

STAGE="swap-temp-to-live"
RESTORE_ERROR_DETAIL="first rename completed, but temporary database could not be renamed to ${DB_NAME}"
docker compose exec -T "${DB_SERVICE}" psql \
  --username="${DB_USER}" --dbname=postgres --set=ON_ERROR_STOP=1 \
  --command="ALTER DATABASE ${TEMP_DB} RENAME TO ${DB_NAME};"
TEMP_RENAMED=1
TEMP_CREATED=0

if [[ "${TEMP_REVISION}" != "${CODE_HEAD}" ]]; then
  STAGE="upgrade-restored-database"
  RESTORE_ERROR_DETAIL="alembic upgrade failed; original database will be restored automatically"
  docker compose run --rm -T --no-deps "${API_SERVICE}" alembic upgrade head
fi

STAGE="restart"
RESTORE_ERROR_DETAIL="database swap succeeded but application restart failed; original database will be restored automatically"
start_app_surface

STAGE="health-check"
RESTORE_ERROR_DETAIL="API did not become healthy within 40 seconds; original database will be restored automatically"
healthy=0
for _attempt in {1..20}; do
  if docker compose exec -T "${API_SERVICE}" python -c \
    'from urllib.request import urlopen; response=urlopen("http://127.0.0.1:8000/api/v1/health", timeout=2); raise SystemExit(0 if response.status == 200 else 1)' \
    >/dev/null 2>&1; then
    healthy=1
    break
  fi
  sleep 2
done
if (( healthy == 0 )); then
  false
fi

trap - ERR
STAGE="complete"
echo "Restore complete and API health check passed."
echo "Dump: ${DUMP_FILE}"
echo "Dump revision: ${TEMP_REVISION}"
echo "Code revision: ${CODE_HEAD}"
echo "Original database retained as safety net: ${SAFETY_DB}"
echo "After verification, prune it with:"
echo "  docker compose exec -T db dropdb -U mobility ${SAFETY_DB}"
