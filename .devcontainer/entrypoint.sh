#!/usr/bin/env bash
set -euo pipefail

# Seed or merge LLM-related env into .env so the Wizard picks it up
if [[ -f .devcontainer/.env ]]; then
  # If no .env exists, copy entirely
  if [[ ! -f .env ]]; then
    echo "[entrypoint] Seeding .env from .devcontainer/.env"
    cp .devcontainer/.env .env
  else
    # Merge only the LLM-related keys if missing in .env
    ensure_kv() {
      local key="$1"
      local src=".devcontainer/.env"
      if ! grep -E "^${key}=" -q .env && grep -E "^${key}=" -q "$src"; then
        local val
        val=$(grep -E "^${key}=" "$src" | tail -n1)
        echo "$val" >> .env
        echo "[entrypoint] Added ${key} to .env from .devcontainer/.env"
      fi
    }
    # Prefer new ZYRA_* keys; keep DATAVIZHUB_* for compatibility
    ensure_kv ZYRA_LLM_PROVIDER
    ensure_kv ZYRA_LLM_MODEL
    ensure_kv DATAVIZHUB_LLM_PROVIDER
    ensure_kv DATAVIZHUB_LLM_MODEL
    ensure_kv OLLAMA_BASE_URL
    ensure_kv OPENAI_BASE_URL
  fi
fi

# Export all variables from .env into the container environment (dev only)
if [[ "${ZYRA_ENV:-${DATAVIZHUB_ENV:-dev}}" == "dev" && -f .env ]]; then
  echo "[entrypoint] Loading environment variables from .env (dev only)"
  set -a
  source .env
  set +a
fi

# ====== SERVICE START SECTION ======
# Prefer ZYRA_* env names with legacy fallbacks
AUTOSTART_API=${ZYRA_AUTOSTART_API:-${DATAVIZHUB_AUTOSTART_API:-1}}
AUTOSTART_RQ=${ZYRA_AUTOSTART_RQ:-${DATAVIZHUB_AUTOSTART_RQ:-${ZYRA_USE_REDIS:-${DATAVIZHUB_USE_REDIS:-0}}}}
API_HOST=${ZYRA_API_HOST:-${DATAVIZHUB_API_HOST:-0.0.0.0}}
API_PORT=${ZYRA_API_PORT:-${DATAVIZHUB_API_PORT:-8000}}

# Map ZYRA_* -> DATAVIZHUB_* for runtime back-compat if legacy vars are unset
map_keys=(
  USE_REDIS REDIS_URL AUTOSTART_API AUTOSTART_RQ UPLOAD_DIR MIN_DISK_MB REQUIRE_FFMPEG
  API_HOST API_PORT VERBOSITY STRICT_ENV DEFAULT_STDIN
  CORS_ALLOW_ALL CORS_ORIGINS API_KEY API_KEY_HEADER
  RESULTS_TTL_SECONDS RESULTS_CLEAN_INTERVAL_SECONDS RESULTS_DIR QUEUE
  LLM_PROVIDER LLM_MODEL WIZARD_EDITOR_MODE
)
for k in "${map_keys[@]}"; do
  zy="ZYRA_${k}"
  dv="DATAVIZHUB_${k}"
  if [[ -n "${!zy:-}" && -z "${!dv:-}" ]]; then
    export "${dv}=${!zy}"
  fi
done

mkdir -p .cache
echo "[entrypoint] ===== $(date) API session =====" >> .cache/api.log
echo "[entrypoint] ===== $(date) RQ worker session =====" >> .cache/rq.log

wait_for_redis() {
  local url host port
  url="${ZYRA_REDIS_URL:-${DATAVIZHUB_REDIS_URL:-redis://redis:6379/0}}"
  # Basic validation to avoid accidental command injection or bad values
  if ! [[ "$url" =~ ^redis://[A-Za-z0-9._-]+(:[0-9]{1,5})?(/[0-9]+)?$ ]]; then
    echo "[entrypoint] ERROR: Invalid REDIS_URL: "$url"" >&2
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
  if pgrep -f "rq worker zyra" >/dev/null 2>&1; then
    echo "[entrypoint] RQ worker already running"
  else
    echo "[entrypoint] Starting RQ worker..."
    ( DATAVIZHUB_USE_REDIS=1 ZYRA_USE_REDIS=1 poetry run rq worker zyra >> .cache/rq.log 2>&1 & )
  fi
}

start_api() {
  if pgrep -f "uvicorn zyra.api.server:app" >/dev/null 2>&1; then
    echo "[entrypoint] API already running"
  else
    echo "[entrypoint] Starting API on ${API_HOST}:${API_PORT}"
    ( poetry run uvicorn zyra.api.server:app --host "${API_HOST}" --port "${API_PORT}" --reload >> .cache/api.log 2>&1 & )
  fi
}

if [[ "$AUTOSTART_RQ" == "1" && "${ZYRA_USE_REDIS:-${DATAVIZHUB_USE_REDIS:-0}}" == "1" ]]; then
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
