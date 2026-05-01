FROM python:3.12-slim AS build
WORKDIR /src
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

FROM python:3.12-slim
RUN useradd -u 10001 -m -s /usr/sbin/nologin app && mkdir -p /data && chown -R app:app /data
WORKDIR /app
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

USER app
ENV LOG_LEVEL=INFO \
    DB_PATH=/data/state.db \
    POLL_INTERVAL_SECONDS=60

VOLUME ["/data"]

ENTRYPOINT ["mail-to-hero"]
