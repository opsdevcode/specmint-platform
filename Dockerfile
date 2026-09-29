# syntax=docker/dockerfile:1.7
FROM python:3.12.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    CUE_BIN=/usr/local/bin/cue \
    BIND_HOST=0.0.0.0 \
    PORT=8080

WORKDIR /app

COPY cue/VERSION /tmp/cue/VERSION
COPY tools/cue.sha256 /tmp/cue/cue.sha256
COPY scripts/install-cue.sh /tmp/cue/install-cue.sh

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && mkdir -p /tmp/cue-src/cue /tmp/cue-src/tools /tmp/cue-src/scripts \
    && cp /tmp/cue/VERSION /tmp/cue-src/cue/VERSION \
    && cp /tmp/cue/cue.sha256 /tmp/cue-src/tools/cue.sha256 \
    && cp /tmp/cue/install-cue.sh /tmp/cue-src/scripts/install-cue.sh \
    && bash /tmp/cue-src/scripts/install-cue.sh \
    && install -m 0755 /tmp/cue-src/tools/cue /usr/local/bin/cue \
    && /usr/local/bin/cue version \
    && apt-get purge -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /tmp/cue /tmp/cue-src

COPY pyproject.toml /app/pyproject.toml
COPY src /app/src
COPY cue /app/cue
COPY migrations /app/migrations

ENV SPECMINT_ENV=development \
    SPECMINT_BOOTSTRAP=1 \
    SPECMINT_ALLOW_MEMORY_STORE=1

RUN pip install --no-cache-dir --upgrade pip==25.1.1 \
    && pip install --no-cache-dir "/app[durable]" \
    && useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

USER 10001
EXPOSE 8080
CMD ["python", "-m", "opsdevcode_specmint.main"]
