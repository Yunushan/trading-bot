# Trading Bot Service API

Canonical product launcher for the headless FastAPI service.

The service implementation still lives in `Languages/Python/app/service/` while
the repo finishes its product-first layout migration. This folder is the stable
top-level app boundary for backend packaging and operator-facing launch docs.

## Run

From the repository root with the Python environment already activated:

```bash
python apps/service-api/main.py --serve --host 127.0.0.1 --port 8000
```

Deprecated compatibility launchers still work:

```bash
cd Languages/Python
python -m app.service.main --serve --host 127.0.0.1 --port 8000
```
