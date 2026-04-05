from __future__ import annotations

import os
from dataclasses import dataclass


DEFAULT_API_KEY_ENV = "BINANCE_API_KEY"
DEFAULT_API_SECRET_ENV = "BINANCE_API_SECRET"


@dataclass(frozen=True, slots=True)
class AuthSettings:
    api_key: str = ""
    api_secret: str = ""

    @classmethod
    def from_env(
        cls,
        *,
        api_key_env: str = DEFAULT_API_KEY_ENV,
        api_secret_env: str = DEFAULT_API_SECRET_ENV,
    ) -> "AuthSettings":
        return cls(
            api_key=str(os.getenv(api_key_env, "")),
            api_secret=str(os.getenv(api_secret_env, "")),
        )

    def to_config_dict(self) -> dict[str, str]:
        return {
            "api_key": self.api_key,
            "api_secret": self.api_secret,
        }
