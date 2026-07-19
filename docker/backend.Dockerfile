# syntax=docker/dockerfile:1.7
FROM python:3.14.6-slim-bookworm@sha256:86f975aca15cf04a40b399eebede9aea7c82eae084d1f1a0a6ef6bcaae871a30

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY apps/service-api /app/apps/service-api
COPY apps/web-dashboard /app/apps/web-dashboard
COPY Languages/Python/pyproject.toml Languages/Python/README.md /app/Languages/Python/
COPY Languages/Python/app /app/Languages/Python/app
COPY Languages/Python/trading_core /app/Languages/Python/trading_core

# `pip_ca` is an optional BuildKit secret for enterprise TLS-inspection CAs.
# It is available only during this layer and never copied into the image.
RUN --mount=type=secret,id=pip_ca,required=false,target=/run/secrets/pip_ca \
    if [ -s /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    python -m pip install --upgrade "pip==26.1.2" \
    && pip install ./Languages/Python[service] \
    && useradd --create-home --uid 10001 --user-group --shell /usr/sbin/nologin tradingbot \
    && chown -R tradingbot:tradingbot /app

EXPOSE 8000

USER tradingbot

ENV HOME=/home/tradingbot

CMD ["python", "apps/service-api/main.py", "--serve", "--host", "0.0.0.0", "--port", "8000"]
