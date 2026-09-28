# syntax=docker/dockerfile:1
# Fleet service image: dependencies pinned by uv.lock, non-root, data on a volume.

FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

FROM python:3.12-slim
RUN useradd --system --uid 10001 --home-dir /app fleet \
    && mkdir /data && chown fleet:fleet /data
COPY --from=build --chown=fleet:fleet /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    SARGCS_HOST=0.0.0.0 \
    SARGCS_DATA_DIR=/data
USER fleet
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"]
CMD ["fleet-service"]
