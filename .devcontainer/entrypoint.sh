#!/usr/bin/env bash
set -euo pipefail

# ====== WIKI SYNC SECTION ======
FORCE_UPDATE=0
REFRESH_SECONDS=${DOCS_REFRESH_SECONDS:-3600} # default 1 hour

while [[ ${1:-} ]]; do
  case "$1" in
    --force) FORCE_UPDATE=1; shift ;;
    --refresh-seconds) REFRESH_SECONDS="$2"; shift 2 ;;
    *) echo "[entrypoint] Unknown option: $1" >&2; exit 2 ;;
  esac
done

# Copy default .env if missing
if [[ ! -f .env && -f .devcontainer/.env ]]; then
  echo "[entrypoint] Seeding .env from .devcontainer/.env"
  cp .devcontainer/.env .env
fi

WIKI_URL="https://github.com/NOAA-GSL/datavizhub.wiki.git"
DOCS_DIR="wiki"
META_FILE="$DOCS_DIR/.mirror_meta"

# Fix stale, non-writable wiki dirs
if [[ -d "$DOCS_DIR" && ! -w "$DOCS_DIR" ]]; then
  echo "[entrypoint] Existing $DOCS_DIR not writable — removing"
  rm -rf "$DOCS_DIR" || true
fi

now_epoch() { date +%s; }
should_update=0

if [[ ! -d "$DOCS_DIR" ]]; then
  should_update=1
elif [[ $FORCE_UPDATE -eq 1 ]]; then
  should_update=1
else
  last_sync=0
  if [[ -f "$META_FILE" ]]; then
    source "$META_FILE" || true
    last_sync=${last_sync_epoch:-0}
  fi
  now=$(now_epoch)
  age=$(( now - last_sync ))
  if (( age >= REFRESH_SECONDS )); then
    should_update=1
  fi
fi

if [[ $should_update -eq 1 ]]; then
  echo "[entrypoint] Cloning wiki..."
  tmp_dir="${DOCS_DIR}.new"
  rm -rf "$tmp_dir"
  if git clone --depth=1 "$WIKI_URL" "$tmp_dir"; then
    rm -rf "$tmp_dir/.git"
    echo "source_url=\"$WIKI_URL\"" > "$tmp_dir/.mirror_meta"
    echo "last_sync_epoch=$(now_epoch)" >> "$tmp_dir/.mirror_meta"
    rm -rf "$DOCS_DIR" || true
    mv "$tmp_dir" "$DOCS_DIR" || cp -R "$tmp_dir"/. "$DOCS_DIR"
    rm -rf "$tmp_dir"
    echo "[entrypoint] Wiki synced"
  else
    echo "[entrypoint] WARN: Wiki clone failed; leaving existing wiki"
    rm -rf "$tmp_dir"
  fi
else
  echo "[entrypoint] Wiki is fresh; skipping sync"
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

[[ "$AUTOSTART_RQ" == "1" ]] && start_rq_worker
[[ "$AUTOSTART_API" == "1" ]] && start_api

# Keep container running
tail -f /dev/null
