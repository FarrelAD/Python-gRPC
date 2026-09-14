# =============================================================
# Stage 1: Build & Dependency Resolution Stage
# =============================================================
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry

# Copy dependency manifests
COPY pyproject.toml poetry.lock* README.md /build/

# Create a standalone virtual environment in /build/.venv
RUN poetry config virtualenvs.in-project true \
    && poetry install --only main --no-interaction --no-ansi --no-root

# =============================================================
# Stage 2: Final Lean Production Runtime Stage
# =============================================================
FROM python:3.13-slim AS runtime

WORKDIR /app

# Create a non-root application user for container security
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy virtual environment from builder stage
COPY --from=builder /build/.venv /app/.venv

# Copy application source code and entrypoint script
COPY src /app/src
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Change file ownership to non-root user
RUN chown -R appuser:appuser /app

USER appuser

EXPOSE 50051 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["help"]
