"""
Shared contract for canonical and compatibility entrypoints.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductEntrypointContract:
    product: str
    canonical_repo_path: str
    canonical_module: str
    installed_command: str
    compatibility_entrypoint: str
    compatibility_status: str = "deprecated"

    def compatibility_notice(self) -> str:
        return (
            f"Deprecated compatibility {self.product} entrypoint remains available via "
            f"'{self.compatibility_entrypoint}'. Prefer '{self.canonical_repo_path}' "
            f"or the installed command '{self.installed_command}'."
        )


DESKTOP_ENTRYPOINT_CONTRACT = ProductEntrypointContract(
    product="desktop",
    canonical_repo_path="apps/desktop-pyqt/main.py",
    canonical_module="app.desktop.product_main",
    installed_command="trading-bot-desktop",
    compatibility_entrypoint="Languages/Python/main.py",
)

SERVICE_ENTRYPOINT_CONTRACT = ProductEntrypointContract(
    product="service",
    canonical_repo_path="apps/service-api/main.py",
    canonical_module="app.service.product_main",
    installed_command="trading-bot-service",
    compatibility_entrypoint="python -m app.service.main",
)

DEPRECATED_COMPATIBILITY_ENTRYPOINTS = {
    "desktop": DESKTOP_ENTRYPOINT_CONTRACT,
    "service": SERVICE_ENTRYPOINT_CONTRACT,
}
