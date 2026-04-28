# --- Stage 1: Build Stage ---
FROM python:3.14-slim AS builder

# Install uv (Rust-based manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# NEW: Install the compiler and system headers
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    gcc \
    g++ \
    gfortran \
    libopenblas-dev \
    libjpeg-dev \
    libmupdf-dev \
    libffi-dev \
    zlib1g-dev \
    liblapack-dev \
    pkg-config \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*
    
# Set working directory
WORKDIR /app

# Enable bytecode compilation for faster startups
ENV UV_COMPILE_BYTECODE=1

# Copy only dependency files first to leverage Docker cache
COPY pyproject.toml ./

# Install dependencies into a virtual environment
# --frozen ensures we use the exact versions in the lockfile
RUN uv sync --no-dev --no-install-project

# --- Stage 2: Runtime Stage ---
FROM python:3.14-slim

# 1. Grab the uv binary from the official image again
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Copy, with the --chown flag, the virtual environment from the builder stage
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser . .
RUN mkdir -p /home/appuser/.cache && chown -R appuser:appuser /home/appuser
RUN chown appuser:appuser /app
USER appuser

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Switch to the non-root user
USER appuser

# Expose the port (e.g., if using FastAPI)
EXPOSE 8000

# Run the application
CMD ["python", "api/main.py"]
