FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app/Languages/Python

COPY Languages/Python/requirements.backend.txt ./requirements.backend.txt

RUN python -m pip install --upgrade pip \
    && pip install -r requirements.backend.txt

COPY Languages/Python /app/Languages/Python

EXPOSE 8000

CMD ["python", "-m", "app.service.main", "--serve", "--host", "0.0.0.0", "--port", "8000"]
