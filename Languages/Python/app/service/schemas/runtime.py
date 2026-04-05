"""
Runtime descriptor schemas for the current headless service/API layer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import platform
import sys

from ...entrypoint_contract import DESKTOP_ENTRYPOINT_CONTRACT, SERVICE_ENTRYPOINT_CONTRACT


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
class ServiceControlPlaneDescriptor:
    mode: str = "intent-only"
    owner: str = "service-runtime"
    start_supported: bool = False
    stop_supported: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["notes"] = list(self.notes)
        return payload


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
    control_plane: ServiceControlPlaneDescriptor
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["control_plane"] = self.control_plane.to_dict()
        payload["notes"] = list(self.notes)
        return payload


def build_runtime_descriptor(
    *,
    control_plane: ServiceControlPlaneDescriptor | None = None,
) -> ServiceRuntimeDescriptor:
    from ..api_contract import SERVICE_API_STREAM_DASHBOARD_PATH

    service_file = Path(__file__).resolve()
    repo_root = service_file.parents[5]
    return ServiceRuntimeDescriptor(
        service_name="trading-bot-service",
        phase="phase-2-service-api",
        python_entrypoint=SERVICE_ENTRYPOINT_CONTRACT.canonical_repo_path,
        desktop_entrypoint=DESKTOP_ENTRYPOINT_CONTRACT.canonical_repo_path,
        repo_root=str(repo_root),
        platform=platform.platform(),
        python_version=sys.version.split()[0],
        capabilities=ServiceCapabilityFlags(),
        control_plane=control_plane or ServiceControlPlaneDescriptor(),
        notes=(
            "Canonical product launchers now live under apps/.",
            DESKTOP_ENTRYPOINT_CONTRACT.compatibility_notice(),
            "Docker is optional and not required for local usage.",
            (
                f"HTTP API is available through 'python {SERVICE_ENTRYPOINT_CONTRACT.canonical_repo_path} --serve' "
                f"or the installed command '{SERVICE_ENTRYPOINT_CONTRACT.installed_command}'."
            ),
            SERVICE_ENTRYPOINT_CONTRACT.compatibility_notice(),
            "Optional bearer-token auth can protect the HTTP API via BOT_SERVICE_API_TOKEN or --api-token.",
            "A thin same-origin web dashboard is available at '/ui/' when the service API is running.",
            f"The dashboard can follow live service updates over the SSE stream at '{SERVICE_API_STREAM_DASHBOARD_PATH}'.",
        ),
    )
