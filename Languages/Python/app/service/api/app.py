"""
FastAPI application for the service layer.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    _PYTHON_ROOT = Path(__file__).resolve().parents[3]
    if str(_PYTHON_ROOT) not in sys.path:
        sys.path.insert(0, str(_PYTHON_ROOT))
    from app.service.auth import auth_required, resolve_service_api_token, validate_bearer_token
    from app.service.runtime import TradingBotService
else:
    from ..auth import auth_required, resolve_service_api_token, validate_bearer_token
    from ..runtime import TradingBotService

try:
    from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
    from fastapi.responses import RedirectResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel

    FASTAPI_AVAILABLE = True
    _FASTAPI_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - handled via runtime check
    FastAPI = None
    BaseModel = object
    FASTAPI_AVAILABLE = False
    _FASTAPI_IMPORT_ERROR = exc


def _require_fastapi() -> None:
    if FASTAPI_AVAILABLE:
        return
    raise RuntimeError(
        "FastAPI is not installed. Install optional service dependencies first "
        "(for example: pip install -r requirements.service.txt)."
        ) from _FASTAPI_IMPORT_ERROR


def _resolve_web_client_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "clients" / "web"


if FASTAPI_AVAILABLE:

    class StartControlRequest(BaseModel):
        requested_job_count: int = 0
        source: str = "api"


    class StopControlRequest(BaseModel):
        close_positions: bool = False
        source: str = "api"


    class StartFailureRequest(BaseModel):
        reason: str = ""
        source: str = "api"


    class RuntimeStateRequest(BaseModel):
        active: bool
        active_engine_count: int = 0
        source: str = "api"


    class ConfigReplaceRequest(BaseModel):
        config: dict | None = None


    class LogEventRequest(BaseModel):
        message: str
        source: str = "api"
        level: str = "info"


    class AccountSnapshotRequest(BaseModel):
        total_balance: float | None = None
        available_balance: float | None = None
        source: str = "api"


    class PortfolioSnapshotRequest(BaseModel):
        open_position_records: dict | None = None
        closed_position_records: list[dict] | None = None
        closed_trade_registry: dict | None = None
        active_pnl: float | None = None
        active_margin: float | None = None
        closed_pnl: float | None = None
        closed_margin: float | None = None
        total_balance: float | None = None
        available_balance: float | None = None
        source: str = "api"


def create_service_api_app(
    service: TradingBotService | None = None,
    *,
    api_token: str | None = None,
    host_context: str = "standalone-service",
    host_owner: str = "service-process",
):
    _require_fastapi()
    resolved_api_token = resolve_service_api_token(api_token)
    web_client_dir = _resolve_web_client_dir()
    web_ui_available = web_client_dir.is_dir()
    resolved_host_context = str(host_context or "standalone-service").strip() or "standalone-service"
    resolved_host_owner = str(host_owner or "service-process").strip() or "service-process"
    app = FastAPI(
        title="Trading Bot Service API",
        version="0.1.0",
        description="Headless API surface for the Trading Bot service layer.",
    )
    app.state.service = service or TradingBotService()
    app.state.api_token = resolved_api_token
    app.state.web_client_dir = str(web_client_dir) if web_ui_available else ""
    app.state.web_ui_available = web_ui_available
    app.state.service_api_host_context = resolved_host_context
    app.state.service_api_host_owner = resolved_host_owner
    app.state.service_api_streaming = True

    def _service() -> TradingBotService:
        return app.state.service

    def _service_api_meta() -> dict[str, object]:
        return {
            "host_context": app.state.service_api_host_context,
            "host_owner": app.state.service_api_host_owner,
            "auth_required": auth_required(app.state.api_token),
            "web_ui_available": app.state.web_ui_available,
            "sse_available": bool(app.state.service_api_streaming),
        }

    def _health_payload() -> dict[str, object]:
        service_api = _service_api_meta()
        return {
            "status": "ok",
            "service_name": _service().describe_runtime().service_name,
            "auth_required": service_api["auth_required"],
            "web_ui_available": service_api["web_ui_available"],
            "host_context": service_api["host_context"],
            "host_owner": service_api["host_owner"],
            "sse_available": service_api["sse_available"],
            "service_api": service_api,
        }

    def _build_dashboard_payload(*, log_limit: int = 30) -> dict[str, object]:
        payload = dict(_service().get_dashboard_snapshot(log_limit=log_limit))
        payload["service_api"] = _service_api_meta()
        return payload

    def _require_api_auth(authorization: str | None = Header(default=None)):
        if not auth_required(app.state.api_token):
            return
        if validate_bearer_token(authorization, app.state.api_token):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    def _require_stream_auth(token: str | None = None) -> None:
        if not auth_required(app.state.api_token):
            return
        if validate_bearer_token(f"Bearer {token}" if token else None, app.state.api_token):
            return
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if web_ui_available:
        app.mount("/ui", StaticFiles(directory=str(web_client_dir), html=True), name="web-ui")

    @app.get("/")
    def root():
        if app.state.web_ui_available:
            return RedirectResponse(url="/ui/")
        return {"status": "ok", "service_name": _service().describe_runtime().service_name}

    @app.get("/health")
    def health():
        return _health_payload()

    @app.get("/api/runtime", dependencies=[Depends(_require_api_auth)])
    def get_runtime():
        return _service().describe_runtime().to_dict()

    @app.get("/api/dashboard", dependencies=[Depends(_require_api_auth)])
    def get_dashboard(log_limit: int = 30):
        return _build_dashboard_payload(log_limit=log_limit)

    @app.get("/api/status", dependencies=[Depends(_require_api_auth)])
    def get_status():
        return _service().get_status().to_dict()

    @app.get("/api/config-summary", dependencies=[Depends(_require_api_auth)])
    def get_config_summary():
        return _service().get_config_summary().to_dict()

    @app.get("/api/config", dependencies=[Depends(_require_api_auth)])
    def get_config():
        return _service().get_config_payload().to_dict()

    @app.put("/api/config", dependencies=[Depends(_require_api_auth)])
    def replace_config(payload: ConfigReplaceRequest):
        _service().replace_config(payload.config)
        return _service().get_config_payload().to_dict()

    @app.patch("/api/config", dependencies=[Depends(_require_api_auth)])
    def update_config(payload: ConfigReplaceRequest):
        return _service().update_config(payload.config).to_dict()

    @app.put("/api/runtime/state", dependencies=[Depends(_require_api_auth)])
    def set_runtime_state(payload: RuntimeStateRequest):
        result = _service().set_runtime_state(
            active=payload.active,
            active_engine_count=payload.active_engine_count,
            source=payload.source,
        )
        return result.to_dict()

    @app.post("/api/control/start", dependencies=[Depends(_require_api_auth)])
    def request_start(payload: StartControlRequest):
        result = _service().request_start(
            requested_job_count=payload.requested_job_count,
            source=payload.source,
        )
        return result.to_dict()

    @app.post("/api/control/stop", dependencies=[Depends(_require_api_auth)])
    def request_stop(payload: StopControlRequest):
        result = _service().request_stop(
            close_positions=payload.close_positions,
            source=payload.source,
        )
        return result.to_dict()

    @app.post("/api/control/start-failed", dependencies=[Depends(_require_api_auth)])
    def mark_start_failed(payload: StartFailureRequest):
        result = _service().mark_start_failed(
            reason=payload.reason,
            source=payload.source,
        )
        return result.to_dict()

    @app.get("/api/account", dependencies=[Depends(_require_api_auth)])
    def get_account_snapshot():
        return _service().get_account_snapshot().to_dict()

    @app.put("/api/account", dependencies=[Depends(_require_api_auth)])
    def set_account_snapshot(payload: AccountSnapshotRequest):
        snapshot = _service().set_account_snapshot(
            total_balance=payload.total_balance,
            available_balance=payload.available_balance,
            source=payload.source,
        )
        return snapshot.to_dict()

    @app.get("/api/portfolio", dependencies=[Depends(_require_api_auth)])
    def get_portfolio_snapshot():
        return _service().get_portfolio_snapshot().to_dict()

    @app.put("/api/portfolio", dependencies=[Depends(_require_api_auth)])
    def set_portfolio_snapshot(payload: PortfolioSnapshotRequest):
        snapshot = _service().set_portfolio_snapshot(
            open_position_records=payload.open_position_records,
            closed_position_records=payload.closed_position_records,
            closed_trade_registry=payload.closed_trade_registry,
            active_pnl=payload.active_pnl,
            active_margin=payload.active_margin,
            closed_pnl=payload.closed_pnl,
            closed_margin=payload.closed_margin,
            total_balance=payload.total_balance,
            available_balance=payload.available_balance,
            source=payload.source,
        )
        return snapshot.to_dict()

    @app.get("/api/logs", dependencies=[Depends(_require_api_auth)])
    def get_recent_logs(limit: int = 100):
        return [item.to_dict() for item in _service().get_recent_logs(limit=limit)]

    @app.post("/api/logs", dependencies=[Depends(_require_api_auth)])
    def record_log_event(payload: LogEventRequest):
        event = _service().record_log_event(
            payload.message,
            source=payload.source,
            level=payload.level,
        )
        return event.to_dict()

    @app.get("/api/stream/dashboard")
    async def stream_dashboard(
        request: Request,
        token: str | None = Query(default=None),
        log_limit: int = 30,
        interval_ms: int = 1000,
    ):
        _require_stream_auth(token)
        stream_interval = max(250, int(interval_ms)) / 1000.0

        async def event_stream():
            while True:
                if await request.is_disconnected():
                    break
                payload = _build_dashboard_payload(log_limit=log_limit)
                yield f"event: dashboard\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"
                await asyncio.sleep(stream_interval)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            },
        )

    return app


def run_service_api_server(
    *,
    service: TradingBotService | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    api_token: str | None = None,
) -> None:
    _require_fastapi()
    try:
        import uvicorn
    except Exception as exc:  # pragma: no cover - handled via runtime check
        raise RuntimeError(
            "Uvicorn is not installed. Install optional service dependencies first "
            "(for example: pip install -r requirements.service.txt)."
        ) from exc

    app = create_service_api_app(
        service=service,
        api_token=api_token,
        host_context="standalone-service",
        host_owner="service-process",
    )
    uvicorn.run(app, host=str(host or "127.0.0.1"), port=max(1, int(port)), log_level="info")
