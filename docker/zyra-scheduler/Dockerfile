ARG ZYRA_VERSION=latest
ARG WITH_WGRIB2=none
ARG WITH_FFMPEG=true
ARG ZYRA_EXTRAS=""

# Optional builder for source-built wgrib2 (only built if referenced)
FROM debian:stable-slim AS wgrib2-builder
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
ARG WGRIB2_URL="https://ftp.cpc.ncep.noaa.gov/wd51we/wgrib2/wgrib2.tgz"
ARG WGRIB2_SHA256=""
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl build-essential gfortran make zlib1g-dev libpng-dev libjpeg-dev \
    && rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    test -n "$WGRIB2_URL"; \
    curl -fsSLO "$WGRIB2_URL"; \
    if [[ -n "$WGRIB2_SHA256" ]]; then echo "$WGRIB2_SHA256  $(basename "$WGRIB2_URL")" | sha256sum -c -; else echo "Skipping SHA256 verification"; fi; \
    tar -xvzf "$(basename "$WGRIB2_URL")"; \
    cd grib2; \
    make USE_AEC=0 USE_OPENJPEG=0 USE_NETCDF3=0 USE_NETCDF4=0; \
    cp wgrib2/wgrib2 /wgrib2

FROM python:3.11-slim
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Basic runtime env
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    LOG_LEVEL=info \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System deps (ffmpeg used by some visualization/processing flows)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && if [ "$WITH_FFMPEG" = "true" ]; then apt-get install -y --no-install-recommends ffmpeg; fi \
    && if [ "$WITH_WGRIB2" = "apt" ] || [ "$WITH_WGRIB2" = "true" ]; then apt-get install -y --no-install-recommends wgrib2; fi \
    && rm -rf /var/lib/apt/lists/*

# Optionally copy source-built wgrib2
ARG WITH_WGRIB2
COPY --from=wgrib2-builder /wgrib2 /usr/local/bin/wgrib2
RUN if [[ "$WITH_WGRIB2" != "source" ]]; then rm -f /usr/local/bin/wgrib2 || true; fi

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
    fi

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
