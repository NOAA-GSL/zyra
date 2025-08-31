# zyra-scheduler container

A minimal, scheduler-only image that watches a workflows directory and runs
Zyra pipelines. It exposes two mount points:

- `/workflows`: read-only workflows (YAML) to execute
- `/data`: outputs, logs, and artifacts (also available via `$DATA_DIR`)

The image does not run the API by default.

## Image

- Registry: `ghcr.io/noaa-gsl/zyra-scheduler`
- Tags: `vX.Y.Z`, `latest` (non-prerelease), and `sha-…`
- Build args:
  - `ZYRA_VERSION` (default `latest`): pin Zyra from PyPI
  - `WITH_FFMPEG` (default `true`): install `ffmpeg` via apt
  - `WITH_WGRIB2` (default `none`): how to include `wgrib2`.
    - `none` (or `false`): do not include `wgrib2`
    - `apt` (or `true`): install Debian package `wgrib2`
    - `source`: build from source in a builder stage (requires BuildKit)
  - `WGRIB2_URL` and `WGRIB2_SHA256` (with `WITH_WGRIB2=source`): tarball URL and optional checksum
  - `ZYRA_EXTRAS` (default empty): install `zyra[extras]` from PyPI (e.g., `connectors,processing`)

## Quick start (Docker)

```bash
# Workflows and data directories
mkdir -p workflows data

# Run latest release
docker run -d \
  --name zyra-scheduler \
  -v "$(pwd)/workflows:/workflows:ro" \
  -v "$(pwd)/data:/data" \
  -e LOG_LEVEL=info \
  ghcr.io/noaa-gsl/zyra-scheduler:latest
```

## docker-compose

An example compose file is provided at `docker-compose.yml`:

```bash
cd docker/zyra-scheduler
mkdir -p ../../workflows ../../data
# Create a local .env from the template (optional)
cp -n .env.example .env || true
# Optionally pin a tag (e.g., to use a -grib variant if published)
# echo "ZYRA_TAG=vX.Y.Z" > .env

docker compose up -d
```

## Notes

- Permissions: The container runs as a non-root user (`uid=10001`). If you hit
  permissions issues with bind mounts on Linux, you can uncomment the `user:`
  line in `docker-compose.yml` (e.g. `user: "${UID}:${GID}").
- FFmpeg: Installed by default; disable at build time with `--build-arg WITH_FFMPEG=false` if not needed.
- GRIB: For pipelines that require `wgrib2`, build with `--build-arg WITH_WGRIB2=apt` (Debian package)
  or `--build-arg WITH_WGRIB2=source` (BuildKit required). If you publish a variant tag that includes
  `wgrib2`, you can also reference that tag directly.
- API: Not started by default; override `command`/`entrypoint` if needed.

## Build examples

```bash
# Build with wgrib2 from apt
docker build -f docker/zyra-scheduler/Dockerfile \
  --build-arg WITH_WGRIB2=apt \
  -t zyra-scheduler:apt .

# Build with wgrib2 from source
DOCKER_BUILDKIT=1 docker build -f docker/zyra-scheduler/Dockerfile \
  --build-arg WITH_WGRIB2=source \
  --build-arg WGRIB2_URL=https://ftp.cpc.ncep.noaa.gov/wd51we/wgrib2/wgrib2.tgz \
  -t zyra-scheduler:source .

# Build without wgrib2 (default)
docker build -f docker/zyra-scheduler/Dockerfile \
  --build-arg WITH_WGRIB2=none \
  -t zyra-scheduler:slim .
```
