########################
# === Base Stage ===
########################
FROM python:3.10-slim AS base

# Set environment variables to prevent Python from writing .pyc files and buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV CC gcc
ENV FC gfortran
ENV USE_AEC 0
ENV USE_NETCDF3 0
ENV USE_NETCDF4 0

# Set the working directory in the container
WORKDIR /app

# Install system dependencies, including gfortran, build tools, and libraries required to build wgrib2
RUN apt-get update && apt-get install -y \
    curl \
    bash \
    build-essential \
    musl-dev \
    gfortran \
    ffmpeg \
    make \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    git \
    git-lfs \
    procps \
 && rm -rf /var/lib/apt/lists/*
 
RUN git lfs install

# Install wgrib2 from source, disable AEC, OpenJPEG, and NetCDF support by passing flags to make
RUN curl -O https://ftp.cpc.ncep.noaa.gov/wd51we/wgrib2/wgrib2.tgz \
    && tar -xvzf wgrib2.tgz \
    && cd grib2 \
    && make USE_AEC=0 USE_OPENJPEG=0 USE_NETCDF3=0 USE_NETCDF4=0 \
    && cp wgrib2/wgrib2 /usr/local/bin/ \
    && cd .. && rm -rf grib2 wgrib2.tgz

# Upgrade pip to the latest version
RUN pip install --upgrade pip

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
ENV PATH="/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin:/root/.local/bin:$PATH"

# Copy pyproject.toml and poetry.lock files first (this helps with Docker caching)
COPY pyproject.toml poetry.lock /app/

# Install all dependencies (dev + extras) without installing the package itself
RUN poetry install --no-root --with dev --all-extras

# Copy the rest of the application code
COPY . /app

########################
# === Dev Stage ===
########################

FROM base AS dev

# Install Node.js for Codex CLI
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g @openai/codex

# Install project with dev + all extras (editable install via Poetry)
RUN poetry install --with dev --all-extras

# Healthcheck for non-compose runs
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD sh -c "curl -fsS http://localhost:${DATAVIZHUB_API_PORT:-8000}/ready || exit 1"

# Set the default command to open a bash shell
CMD ["sleep", "infinity"]
