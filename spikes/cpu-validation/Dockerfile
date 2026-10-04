ARG PYTHON_VERSION=3.14
FROM python:${PYTHON_VERSION}-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Docling's table model imports OpenCV, which needs these shared libraries
# that the slim image leaves out.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libxcb1 \
    && rm -rf /var/lib/apt/lists/*

# The virtualenv lives outside /app so the bind mount of the spike directory
# does not hide it. Model downloads go to /models, which compose backs with a volume.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/models/hf \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
RUN uv sync --no-install-project --no-cache

# Scripts are not copied in: compose bind-mounts this directory at /app.
CMD ["python", "run.py"]
