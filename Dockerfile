FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install poetry
RUN pip install --no-cache-dir poetry

COPY pyproject.toml poetry.lock* README.md /app/
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

COPY src /app/src
ENV PYTHONPATH=/app/src

EXPOSE 50051 8000

CMD ["python", "-m", "python_grpc.server"]
