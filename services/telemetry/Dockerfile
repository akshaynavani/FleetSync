# syntax=docker/dockerfile:1.7
# Build context is services/ so the shared fleetsync_common package can be copied in.

FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /build
COPY telemetry/requirements.txt .
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
LABEL org.opencontainers.image.title="fleetsync-telemetry" \
      org.opencontainers.image.source="https://github.com/akshaynavani/FleetSync"
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8001
RUN groupadd --system --gid 10001 fleet && useradd --system --uid 10001 --gid fleet --no-create-home fleet
COPY --from=builder /install /usr/local
WORKDIR /srv
COPY common/fleetsync_common ./fleetsync_common
COPY telemetry/app ./app
USER 10001
EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz', timeout=2)"
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers ${UVICORN_WORKERS:-1} --no-access-log"]
