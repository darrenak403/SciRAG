FROM python:3.14-slim AS base

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

# The virtualenv lives outside /app so the dev bind mounts do not hide it.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src:/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies sit in their own layer: editing source does not reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-cache

# API image: no Docling, no PyTorch.
FROM base AS api
COPY alembic.ini ./
COPY src ./src
COPY apps ./apps
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Worker image: adds the PDF parsing stack on top of the shared dependencies.
FROM base AS worker
# Docling's table model imports OpenCV, which needs these shared libraries
# that the slim image leaves out.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxcb1 \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-install-project --no-cache --group ingest
# Parser model weights are downloaded here on first use; compose backs it with a volume.
ENV HF_HOME=/models/hf
COPY alembic.ini ./
COPY src ./src
COPY apps ./apps
CMD ["python", "-m", "apps.worker.main"]
