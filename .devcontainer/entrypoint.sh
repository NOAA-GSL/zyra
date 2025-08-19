#!/usr/bin/env bash
set -euo pipefail

# Copy default .env if missing
if [[ ! -f .env && -f .devcontainer/.env ]]; then
  echo "[entrypoint] Seeding .env from .devcontainer/.env"
  cp .devcontainer/.env .env
fi

# ====== SERVICE START SECTION ======
AUTOSTART_API=${DATAVIZHUB_AUTOSTART_API:-1}
AUTOSTART_RQ=${DATAVIZHUB_AUTOSTART_RQ:-${DATAVIZHUB_USE_REDIS:-0}}
API_HOST=${DATAVIZHUB_API_HOST:-0.0.0.0}
API_PORT=${DATAVIZHUB_API_PORT:-8000}

mkdir -p .cache
echo "[entrypoint] ===== $(date) API session =====" >> .cache/api.log
echo "[entrypoint] ===== $(date) RQ worker session =====" >> .cache/rq.log

wait_for_redis() {
  local url host port
  url="${DATAVIZHUB_REDIS_URL:-redis://redis:6379/0}"
  # Basic validation to avoid accidental command injection or bad values
  if ! [[ "$url" =~ ^redis://[A-Za-z0-9._-]+(:[0-9]{1,5})?(/[0-9]+)?$ ]]; then
    echo "[entrypoint] ERROR: Invalid DATAVIZHUB_REDIS_URL: "$url"" >&2
    return 1
  fi
  host=$(echo "$url" | sed -E 's#^redis://([^:/]+):?([0-9]+)?.*#\1#')
  port=$(echo "$url" | sed -E 's#^redis://([^:/]+):?([0-9]+)?.*#\2#')
  [[ -z "$port" ]] && port=6379
  echo "[entrypoint] Waiting for Redis at ${host}:${port}"
  for i in {1..30}; do
    if (echo > "/dev/tcp/${host}/${port}") >/dev/null 2>&1; then
      echo "[entrypoint] Redis is ready"
      return 0
    fi
    sleep 1
  done
  echo "[entrypoint] ERROR: Redis not reachable after timeout" >&2
  return 1
}

start_rq_worker() {
  if pgrep -f "rq worker datavizhub" >/dev/null 2>&1; then
    echo "[entrypoint] RQ worker already running"
  else
    echo "[entrypoint] Starting RQ worker..."
    ( DATAVIZHUB_USE_REDIS=1 poetry run rq worker datavizhub >> .cache/rq.log 2>&1 & )
  fi
}

start_api() {
  if pgrep -f "uvicorn datavizhub.api.server:app" >/dev/null 2>&1; then
    echo "[entrypoint] API already running"
  else
    echo "[entrypoint] Starting API on ${API_HOST}:${API_PORT}"
    ( poetry run uvicorn datavizhub.api.server:app --host "${API_HOST}" --port "${API_PORT}" --reload >> .cache/api.log 2>&1 & )
  fi
}

if [[ "$AUTOSTART_RQ" == "1" && "$DATAVIZHUB_USE_REDIS" == "1" ]]; then
  wait_for_redis || exit 1
fi

if [[ "$AUTOSTART_RQ" == "1" ]]; then
  start_rq_worker
fi
if [[ "$AUTOSTART_API" == "1" ]]; then
  start_api
fi

# Keep container running
tail -f /dev/null
