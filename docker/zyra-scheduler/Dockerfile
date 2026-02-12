# syntax=docker/dockerfile:1.6
ARG ZYRA_VERSION=latest
ARG WITH_WGRIB2=none
ARG WITH_FFMPEG=true
ARG ZYRA_EXTRAS="connectors"

# Optional builder for source-built wgrib2 (only built if referenced)
FROM debian:stable-slim AS wgrib2-builder
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG WGRIB2_URL="https://ftp.cpc.ncep.noaa.gov/wd51we/wgrib2/wgrib2.tgz"
ARG WGRIB2_SHA256=""
ARG WITH_WGRIB2=none
ARG TARGETARCH
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl build-essential gfortran make zlib1g-dev libpng-dev libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    mkdir -p /out; \
    if [[ "$WITH_WGRIB2" != "source" ]]; then \
      echo "Skipping wgrib2 build (WITH_WGRIB2=$WITH_WGRIB2)"; \
    elif [[ "${TARGETARCH:-}" != "amd64" ]]; then \
      echo "Skipping wgrib2 source build on TARGETARCH=${TARGETARCH:-unknown}; will install via apt in final stage"; \
    else \
      test -n "$WGRIB2_URL"; \
      curl -fsSLO "$WGRIB2_URL"; \
      if [[ -n "$WGRIB2_SHA256" ]]; then echo "$WGRIB2_SHA256  $(basename "$WGRIB2_URL")" | sha256sum -c -; else echo "WARNING: Skipping SHA256 verification (WGRIB2_SHA256 not set)"; fi; \
      tar -xvzf "$(basename "$WGRIB2_URL")"; \
      cd grib2; \
      make CC=gcc FC=gfortran USE_AEC=0 USE_OPENJPEG=0 USE_NETCDF3=0 USE_NETCDF4=0; \
      cp wgrib2/wgrib2 /out/wgrib2; \
    fi

FROM python:3.11-slim
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Basic runtime env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    LOG_LEVEL=info \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG TARGETARCH
# Re-declare build args in this stage so they are visible
ARG WITH_FFMPEG=true
ARG WITH_WGRIB2=none
# System deps (ffmpeg used by some visualization/processing flows)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && FF_FLAG="${WITH_FFMPEG,,}"; if [ "$FF_FLAG" = "true" ] || [ "$FF_FLAG" = "1" ] || [ "$FF_FLAG" = "yes" ]; then \
         echo "Installing ffmpeg (WITH_FFMPEG=$WITH_FFMPEG)"; \
         apt-get install -y --no-install-recommends ffmpeg; \
         # Ensure binaries are visible on PATH even in restricted envs
         if command -v ffmpeg >/dev/null 2>&1; then ln -sf "$(command -v ffmpeg)" /usr/local/bin/ffmpeg; fi; \
         if command -v ffprobe >/dev/null 2>&1; then ln -sf "$(command -v ffprobe)" /usr/local/bin/ffprobe; fi; \
       else \
         echo "Skipping ffmpeg (WITH_FFMPEG=$WITH_FFMPEG)"; \
       fi \
    && if [ "$WITH_WGRIB2" = "apt" ] || [ "$WITH_WGRIB2" = "true" ] || { [ "$WITH_WGRIB2" = "source" ] && [ "${TARGETARCH}" != "amd64" ]; }; then \
         echo "Installing wgrib2 via apt (WITH_WGRIB2=$WITH_WGRIB2, TARGETARCH=${TARGETARCH})"; \
         apt-get install -y --no-install-recommends wgrib2; \
       fi \
    && rm -rf /var/lib/apt/lists/*

# Optionally install source-built wgrib2 without copying when not needed
RUN --mount=type=bind,from=wgrib2-builder,source=/out,target=/tmp/wgrib2,ro \
    set -eux; \
    if [[ "$WITH_WGRIB2" == "source" && "${TARGETARCH}" == "amd64" ]]; then \
      if [[ -s /tmp/wgrib2/wgrib2 ]]; then \
        install -m 0755 /tmp/wgrib2/wgrib2 /usr/local/bin/wgrib2; \
        echo "Installed wgrib2 from source"; \
      else \
        echo "WITH_WGRIB2=source but wgrib2 binary not produced by builder" >&2; \
        exit 1; \
      fi; \
    else \
      echo "Skipping source wgrib2 install (WITH_WGRIB2=$WITH_WGRIB2, TARGETARCH=${TARGETARCH})"; \
    fi

# Install Zyra from PyPI, pin to release if provided
ARG ZYRA_VERSION
ARG ZYRA_EXTRAS
RUN if [ -z "$ZYRA_VERSION" ] || [ "$ZYRA_VERSION" = "latest" ]; then \
      if [ -n "$ZYRA_EXTRAS" ]; then \
        pip install --no-cache-dir --no-compile "zyra[${ZYRA_EXTRAS}]"; \
      else \
        pip install --no-cache-dir --no-compile zyra; \
      fi; \
    else \
      if [ -n "$ZYRA_EXTRAS" ]; then \
        pip install --no-cache-dir --no-compile "zyra[${ZYRA_EXTRAS}]==${ZYRA_VERSION}"; \
      else \
        pip install --no-cache-dir --no-compile "zyra==${ZYRA_VERSION}"; \
      fi; \
    fi \
    && pip install --no-cache-dir --upgrade 'setuptools>=78.1.1' 'wheel>=0.46.2'

# Create mount points and permissions
RUN mkdir -p /workflows /data \
    && groupadd -g 10001 appuser \
    && useradd -u 10001 -g 10001 -m appuser \
    && chown -R appuser:appuser /workflows /data

VOLUME ["/workflows", "/data"]
WORKDIR /workflows
USER appuser

# Lightweight healthcheck: verify CLI is responsive
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD zyra --version >/dev/null 2>&1 || exit 1

# Scheduler-only default: watch workflows directory; no API by default
ENTRYPOINT ["zyra", "run", "/workflows", "--watch"]
