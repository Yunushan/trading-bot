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
    from app.service.api_contract import (
        SERVICE_API_BASE_PATH,
        SERVICE_API_DESCRIPTION,
        SERVICE_API_HEALTH_PATH,
        SERVICE_API_LEGACY_BASE_PATH,
        SERVICE_API_STREAM_DASHBOARD_PATH,
        SERVICE_API_TITLE,
        SERVICE_API_UI_PATH,
        SERVICE_API_VERSION,
    )
    from app.service.auth import auth_required, resolve_service_api_token, validate_bearer_token
    from app.service.runtime import TradingBotService
else:
    from ..api_contract import (
        SERVICE_API_BASE_PATH,
        SERVICE_API_DESCRIPTION,
        SERVICE_API_HEALTH_PATH,
        SERVICE_API_LEGACY_BASE_PATH,
        SERVICE_API_STREAM_DASHBOARD_PATH,
        SERVICE_API_TITLE,
        SERVICE_API_UI_PATH,
        SERVICE_API_VERSION,
    )
    from ..auth import auth_required, resolve_service_api_token, validate_bearer_token
    from ..runtime import TradingBotService

try:
    from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request, status
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
    repo_root = Path(__file__).resolve().parents[5]
    candidates = (
        repo_root / "apps" / "web-dashboard",
        Path(__file__).resolve().parents[3] / "clients" / "web",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


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


    class BacktestRunRequest(BaseModel):
        request: dict | None = None
        source: str = "api"


    class BacktestStopRequest(BaseModel):
        source: str = "api"


def create_service_api_app(
    service: TradingBotService | None = None,
    *,
    api_token: str | None = None,
    host_context: str = "standalone-service",
    host_owner: str = "service-process",
    enable_local_executor: bool | None = None,
):
    _require_fastapi()
    resolved_api_token = resolve_service_api_token(api_token)
    web_client_dir = _resolve_web_client_dir()
    web_ui_available = web_client_dir.is_dir()
    resolved_host_context = str(host_context or "standalone-service").strip() or "standalone-service"
    resolved_host_owner = str(host_owner or "service-process").strip() or "service-process"
    service_instance = service or TradingBotService()
    if enable_local_executor is None:
        enable_local_executor = service is None and resolved_host_context == "standalone-service"
    if enable_local_executor:
        try:
            service_instance.enable_local_executor()
        except Exception:
            pass
    app = FastAPI(
        title=SERVICE_API_TITLE,
        version=SERVICE_API_VERSION,
        description=SERVICE_API_DESCRIPTION,
    )
    app.state.service = service_instance
    app.state.api_token = resolved_api_token
    app.state.web_client_dir = str(web_client_dir) if web_ui_available else ""
    app.state.web_ui_available = web_ui_available
    app.state.service_api_host_context = resolved_host_context
    app.state.service_api_host_owner = resolved_host_owner
    app.state.service_api_streaming = True
    app.state.service_api_version = SERVICE_API_VERSION
    app.state.service_api_base_path = SERVICE_API_BASE_PATH
    app.state.service_api_legacy_base_path = SERVICE_API_LEGACY_BASE_PATH
    app.state.service_api_stream_path = SERVICE_API_STREAM_DASHBOARD_PATH

    def _service() -> TradingBotService:
        return app.state.service

    def _service_api_meta() -> dict[str, object]:
        return {
            "version": app.state.service_api_version,
            "api_base_path": app.state.service_api_base_path,
            "legacy_api_base_path": app.state.service_api_legacy_base_path,
            "dashboard_stream_path": app.state.service_api_stream_path,
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
        app.mount(SERVICE_API_UI_PATH, StaticFiles(directory=str(web_client_dir), html=True), name="web-ui")

    api_router = APIRouter(dependencies=[Depends(_require_api_auth)])
    stream_router = APIRouter()

    @app.get("/")
    def root():
        if app.state.web_ui_available:
            return RedirectResponse(url=f"{SERVICE_API_UI_PATH.rstrip('/')}/")
        return {"status": "ok", "service_name": _service().describe_runtime().service_name}

    @app.get(SERVICE_API_HEALTH_PATH)
    def health():
        return _health_payload()

    @api_router.get("/runtime")
    def get_runtime():
        return _service().describe_runtime().to_dict()

    @api_router.get("/dashboard")
    def get_dashboard(log_limit: int = 30):
        return _build_dashboard_payload(log_limit=log_limit)

    @api_router.get("/status")
    def get_status():
        return _service().get_status().to_dict()

    @api_router.get("/execution")
    def get_execution_snapshot():
        return _service().get_execution_snapshot().to_dict()

    @api_router.get("/backtest")
    def get_backtest_snapshot():
        return _service().get_backtest_snapshot().to_dict()

    @api_router.get("/config-summary")
    def get_config_summary():
        return _service().get_config_summary().to_dict()

    @api_router.get("/config")
    def get_config():
        return _service().get_config_payload().to_dict()

    @api_router.put("/config")
    def replace_config(payload: ConfigReplaceRequest):
        _service().replace_config(payload.config)
        return _service().get_config_payload().to_dict()

    @api_router.patch("/config")
    def update_config(payload: ConfigReplaceRequest):
        return _service().update_config(payload.config).to_dict()

    @api_router.put("/runtime/state")
    def set_runtime_state(payload: RuntimeStateRequest):
        result = _service().set_runtime_state(
            active=payload.active,
            active_engine_count=payload.active_engine_count,
            source=payload.source,
        )
        return result.to_dict()

    @api_router.post("/control/start")
    def request_start(payload: StartControlRequest):
        result = _service().request_start(
            requested_job_count=payload.requested_job_count,
            source=payload.source,
        )
        return result.to_dict()

    @api_router.post("/control/stop")
    def request_stop(payload: StopControlRequest):
        result = _service().request_stop(
            close_positions=payload.close_positions,
            source=payload.source,
        )
        return result.to_dict()

    @api_router.post("/backtest/run")
    def run_backtest(payload: BacktestRunRequest):
        result = _service().submit_backtest(
            payload.request if isinstance(payload.request, dict) else None,
            source=payload.source,
        )
        return result.to_dict()

    @api_router.post("/backtest/stop")
    def stop_backtest(payload: BacktestStopRequest):
        result = _service().stop_backtest(source=payload.source)
        return result.to_dict()

    @api_router.post("/control/start-failed")
    def mark_start_failed(payload: StartFailureRequest):
        result = _service().mark_start_failed(
            reason=payload.reason,
            source=payload.source,
        )
        return result.to_dict()

    @api_router.get("/account")
    def get_account_snapshot():
        return _service().get_account_snapshot().to_dict()

    @api_router.put("/account")
    def set_account_snapshot(payload: AccountSnapshotRequest):
        snapshot = _service().set_account_snapshot(
            total_balance=payload.total_balance,
            available_balance=payload.available_balance,
            source=payload.source,
        )
        return snapshot.to_dict()

    @api_router.get("/portfolio")
    def get_portfolio_snapshot():
        return _service().get_portfolio_snapshot().to_dict()

    @api_router.put("/portfolio")
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

    @api_router.get("/logs")
    def get_recent_logs(limit: int = 100):
        return [item.to_dict() for item in _service().get_recent_logs(limit=limit)]

    @api_router.post("/logs")
    def record_log_event(payload: LogEventRequest):
        event = _service().record_log_event(
            payload.message,
            source=payload.source,
            level=payload.level,
        )
        return event.to_dict()

    @stream_router.get("/stream/dashboard")
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

    app.include_router(api_router, prefix=SERVICE_API_BASE_PATH)
    app.include_router(stream_router, prefix=SERVICE_API_BASE_PATH)
    if SERVICE_API_LEGACY_BASE_PATH != SERVICE_API_BASE_PATH:
        app.include_router(api_router, prefix=SERVICE_API_LEGACY_BASE_PATH, include_in_schema=False)
        app.include_router(stream_router, prefix=SERVICE_API_LEGACY_BASE_PATH, include_in_schema=False)

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
        enable_local_executor=True,
    )
    uvicorn.run(app, host=str(host or "127.0.0.1"), port=max(1, int(port)), log_level="info")
