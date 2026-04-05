FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY apps/service-api /app/apps/service-api
COPY apps/web-dashboard /app/apps/web-dashboard
COPY Languages/Python /app/Languages/Python

RUN python -m pip install --upgrade pip \
    && pip install ./Languages/Python[service]

EXPOSE 8000

CMD ["python", "apps/service-api/main.py", "--serve", "--host", "0.0.0.0", "--port", "8000"]
