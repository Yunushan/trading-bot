"""
Runtime descriptor schemas for the current headless service/API layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import platform
import sys


@dataclass(frozen=True, slots=True)
class ServiceCapabilityFlags:
    desktop_client: bool = True
    local_service_process: bool = True
    remote_http_api: bool = True
    websocket_streams: bool = False
    docker_optional: bool = True
    web_client: bool = True
    mobile_clients: bool = False


@dataclass(frozen=True, slots=True)
class ServiceRuntimeDescriptor:
    service_name: str
    phase: str
    python_entrypoint: str
    desktop_entrypoint: str
    repo_root: str
    platform: str
    python_version: str
    capabilities: ServiceCapabilityFlags
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["notes"] = list(self.notes)
        return payload


def build_runtime_descriptor() -> ServiceRuntimeDescriptor:
    service_file = Path(__file__).resolve()
    repo_root = service_file.parents[5]
    return ServiceRuntimeDescriptor(
        service_name="trading-bot-service",
        phase="phase-2-service-api",
        python_entrypoint="app.service.main",
        desktop_entrypoint="Languages/Python/main.py",
        repo_root=str(repo_root),
        platform=platform.platform(),
        python_version=sys.version.split()[0],
        capabilities=ServiceCapabilityFlags(),
        notes=(
            "Desktop launch remains unchanged.",
            "Docker is optional and not required for local usage.",
            "HTTP API is available through 'python -m app.service.main --serve'.",
            "Optional bearer-token auth can protect the HTTP API via BOT_SERVICE_API_TOKEN or --api-token.",
            "A thin same-origin web dashboard is available at '/ui/' when the service API is running.",
            "The dashboard can follow live service updates over the SSE stream at '/api/stream/dashboard'.",
        ),
    )
