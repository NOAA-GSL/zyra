# Zyra Containers

This directory contains container images for running Zyra in different modes.
Both images are published to GitHub Container Registry (GHCR) on each GitHub
release and support multi-arch (linux/amd64, linux/arm64).

## Images at a Glance

- ghcr.io/noaa-gsl/zyra
  - General-purpose CLI image. Does not auto-start anything.
  - ENTRYPOINT: `zyra`
  - Healthcheck: `zyra --version` (lightweight CLI probe)
  - Includes: `ffmpeg` and `wgrib2` (by default)
  - Volumes: `/workflows` (optional), `/data` (outputs/logs; also `$DATA_DIR`)
  - Best for: CI jobs, ad-hoc local runs, debugging, building your own images.

- ghcr.io/noaa-gsl/zyra-scheduler
  - Long-running scheduler image. Watches workflows and executes them.
  - ENTRYPOINT: `zyra run /workflows --watch`
  - Includes: `ffmpeg` (toggle via `WITH_FFMPEG`); `wgrib2` optional via `WITH_WGRIB2`
  - Healthcheck: `zyra --version` (lightweight CLI probe)
  - Volumes: `/workflows` (read-only recommended), `/data` (outputs/logs)
  - Best for: Daemonized workloads in Docker/Kubernetes.

Tags for both images:
- `vX.Y.Z` (same as the GitHub release tag)
- `latest` (only for non-prerelease tags)
- `sha-…` (content-addressed)

## Quick Pick: Which Image Should I Use?

- Need the CLI for one-off commands or CI? Use `zyra`.
- Need a long-running scheduler that watches a workflows directory? Use `zyra-scheduler`.
- Need the API? Use `zyra` and start it explicitly (the scheduler image does not run the API).

## Volumes and Environment

- `/workflows`: mount your workflow YAMLs here (read-only is recommended).
- `/data`: outputs, logs, and artifacts. Also exposed via `DATA_DIR=/data`.
- Common envs:
  - `DATA_DIR=/data` (default inside the images)
  - `LOG_LEVEL=info` (override as needed)
  - `TZ=UTC` (optional timezone)

## Build-time Options (zyra-scheduler)

You can customize the scheduler image at build time:
- `WITH_FFMPEG` (default `true`): install `ffmpeg` for video/visualization flows.
- `WITH_WGRIB2` (default `none`): how to include `wgrib2`.
  - `none` (default): do not include `wgrib2`.
  - `apt`: install from Debian repos (`apt-get install wgrib2`).
  - `source`: compile from source in a builder stage and copy the binary. Supports checksum verification.
- `WGRIB2_URL` and `WGRIB2_SHA256` (only when `WITH_WGRIB2=source`): tarball URL and optional SHA256 to verify.
- `ZYRA_EXTRAS` (default empty): install pip extras, e.g. `connectors,processing` to get `zyra[connectors,processing]`.

Examples:
```bash
docker build -f docker/zyra-scheduler/Dockerfile \
  --build-arg ZYRA_VERSION=1.2.3 \
  --build-arg WITH_FFMPEG=false \
  --build-arg WITH_WGRIB2=source \
  --build-arg WGRIB2_URL=https://ftp.cpc.ncep.noaa.gov/wd51we/wgrib2/wgrib2.tgz \
  --build-arg WGRIB2_SHA256=<sha256sum> \
  --build-arg ZYRA_EXTRAS=connectors,processing \
  -t ghcr.io/noaa-gsl/zyra-scheduler:custom .
```

The `docker/zyra/Dockerfile` supports the same `WITH_WGRIB2`, `WGRIB2_URL`, and `WGRIB2_SHA256` args. Its default is `WITH_WGRIB2=source`.

## Quick Start

Run the scheduler (watches `/workflows`):

```bash
# From your project directory
mkdir -p workflows data

docker run -d \
  --name zyra-scheduler \
  -v "$(pwd)/workflows:/workflows:ro" \
  -v "$(pwd)/data:/data" \
  -e LOG_LEVEL=info \
  ghcr.io/noaa-gsl/zyra-scheduler:latest
```

Run ad-hoc CLI (no long-running process):

```bash
# Show help
docker run --rm ghcr.io/noaa-gsl/zyra:latest --help

# Run watch mode using the CLI image
mkdir -p workflows data

docker run --rm \
  -v "$(pwd)/workflows:/workflows:ro" \
  -v "$(pwd)/data:/data" \
  ghcr.io/noaa-gsl/zyra:latest run /workflows --watch
```

## docker-compose Examples

Each image directory includes a simple `docker-compose.yml` to get started:

- `docker/zyra/docker-compose.yml` (ad-hoc CLI with convenient mounts)
- `docker/zyra-scheduler/docker-compose.yml` (long-running scheduler)

```bash
# CLI image
cd docker/zyra
mkdir -p ../../workflows ../../data
docker compose run --rm zyra --help

# Scheduler image
cd ../zyra-scheduler
mkdir -p ../../workflows ../../data
docker compose up -d
```

## Scheduling Examples

- Kubernetes CronJob: see `docker/examples/k8s/cronjob-zyra.yaml`.
  - Mount workflows via a `ConfigMap` (or another volume) at `/workflows`.
  - Mount a PVC at `/data` for outputs/logs.
  - Example workflows ConfigMap: `docker/examples/k8s/configmap-workflows.yaml`.
- GitHub Actions schedule: see `docker/examples/ci/github-schedule.yml`.
  - Runs in the `ghcr.io/noaa-gsl/zyra` container on a cron schedule.
- GitLab CI schedule: see `docker/examples/ci/gitlab-schedule.yml`.
  - Uses the `ghcr.io/noaa-gsl/zyra` image with a scheduled pipeline.

## Notes and Troubleshooting

- Permissions: Containers run as a non-root user. If you see write issues with
  bind mounts on Linux, run with `--user $(id -u):$(id -g)` or set `user:` in
  your compose file.
- wgrib2: Included by default in the `zyra` CLI image (built from source). Optional in `zyra-scheduler` to keep it lean (`WITH_WGRIB2=none` by default).
- ffmpeg: Included in both images to support video/visualization flows.
- API: Not started automatically. Start via the CLI image if needed, e.g.:
  `docker run -p 8000:8000 ghcr.io/noaa-gsl/zyra:latest api serve --host 0.0.0.0`.

## Hardened Runtime

For production, run containers with a reduced privilege set and read-only root filesystem. Grant write access only to required mounts (e.g., `/data`). Examples:

```bash
# Minimal hardened run (CLI image)
docker run --rm \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --pids-limit 512 \
  --memory 2g \
  -v "$(pwd)/data:/data" \
  ghcr.io/noaa-gsl/zyra:latest --help

# Hardened API example (bind to localhost; require API key)
docker run --rm \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  -p 127.0.0.1:8000:8000 \
  -e ZYRA_API_KEY=change-me \
  -e CORS_ORIGINS=https://your.domain \
  -v "$(pwd)/data:/data" \
  ghcr.io/noaa-gsl/zyra:latest api serve --host 0.0.0.0 --port 8000
```

Notes:
- Keep `/workflows` read-only for the scheduler; mount `/data` for outputs/logs.
- Add `--tmpfs /tmp:rw,noexec,nosuid` if workloads need temporary scratch space.
- Prefer network egress allowlists in your runtime (Kubernetes NetworkPolicies, etc.).
