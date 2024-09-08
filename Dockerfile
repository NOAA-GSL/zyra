# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables to prevent Python from writing .pyc files and buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies, including cron and ffmpeg
RUN apt-get update && apt-get install -y \
    curl \
    bash \
    build-essential \
    ffmpeg \
    cron \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip to the latest version
RUN pip install --upgrade pip

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | python3 -

# Add Poetry to PATH
ENV PATH="/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin:/root/.local/bin:$PATH"

# Copy pyproject.toml and poetry.lock files first (this helps with Docker caching)
COPY pyproject.toml poetry.lock /app/

# Install dependencies without installing the actual package
RUN poetry install --no-root --only main

# Copy the rest of the application code
COPY . /app

# Build the project (creates a .whl or .tar.gz file in the dist/ folder)
RUN poetry build

# Install the built package inside the Docker container
RUN pip install dist/*.whl

# Copy the cron file into the container
COPY ./config/real-time-video.cron /etc/cron.d/config/real-time-video.cron

# Give execution rights on the cron file
RUN chmod 0644 /etc/cron.d/config/real-time-video.cron

# Apply the cron job
RUN crontab /etc/cron.d/config/real-time-video.cron

# Create the log file to be able to run tail
RUN touch /var/log/cron.log

# Start cron in the foreground
CMD ["cron", "-f"]

# Set the default command to open a bash shell
#CMD ["/bin/bash"]
