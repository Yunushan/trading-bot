# syntax=docker/dockerfile:1.7
#
# The Chainguard Python images are pinned by immutable multi-platform digests.
# The builder contains pip and build tools; the final Wolfi runtime is distroless.
FROM cgr.dev/chainguard/python:latest-dev@sha256:31d318170df60ddec4b04ed595cbe79c33eeb2cf94f9676db6f9eaf46542e6be AS builder

USER root

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

WORKDIR /build

COPY Languages/Python/pyproject.toml Languages/Python/README.md /build/Languages/Python/
COPY Languages/Python/app /build/Languages/Python/app
COPY Languages/Python/trading_core /build/Languages/Python/trading_core

# `pip_ca` is an optional BuildKit secret for enterprise TLS-inspection CAs.
# It is available only during this layer and never copied into the image.
RUN --mount=type=secret,id=pip_ca,required=false,target=/run/secrets/pip_ca \
    if [ -s /run/secrets/pip_ca ]; then export PIP_CERT=/run/secrets/pip_ca; fi; \
    apk add --no-cache build-base linux-headers \
    && python -m venv "$VIRTUAL_ENV" \
    && python -m pip install --upgrade "pip==26.1.2" \
    && pip install /build/Languages/Python[service]

FROM cgr.dev/chainguard/python:latest@sha256:2c6a2e8bdeb1336cd8545d3586d1c1e5b4f7564ef00924b0447ebfbe57a549ee

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HOME=/home/nonroot

WORKDIR /app

COPY --from=builder --chown=65532:65532 /opt/venv /opt/venv
COPY --chown=65532:65532 apps/service-api /app/apps/service-api
COPY --chown=65532:65532 apps/web-dashboard /app/apps/web-dashboard
COPY --chown=65532:65532 Languages/Python/app /app/Languages/Python/app
COPY --chown=65532:65532 Languages/Python/trading_core /app/Languages/Python/trading_core

EXPOSE 8000

USER 65532

ENTRYPOINT ["/opt/venv/bin/python"]
CMD ["apps/service-api/main.py", "--serve", "--host", "0.0.0.0", "--port", "8000"]
