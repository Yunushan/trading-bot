from __future__ import annotations

from . import controls_shared_runtime as shared


def _override_debug_enabled(self) -> bool:
    return bool(getattr(self, "_override_debug_verbose", False) or self.config.get("debug_override_verbose", False))


def _log_override_debug(self, kind: str, message: str, *, payload: dict | None = None) -> None:
    if not self._override_debug_enabled():
        return
    try:
        suffix = ""
        if payload:
            try:
                import json

                suffix = f" :: {json.dumps(payload, default=str, ensure_ascii=False)}"
            except Exception:
                suffix = f" :: {payload}"
        self.log(f"[Override-{kind}] {message}{suffix}")
    except Exception:
        pass


def _normalize_strategy_controls(self, kind: str, controls) -> dict:
    if not isinstance(controls, dict):
        return {}
    normalized: dict[str, object] = {}
    if kind == "runtime":
        side_raw = str(controls.get("side") or "").upper()
        if side_raw in shared.side_labels():
            normalized["side"] = side_raw
        pos_pct = controls.get("position_pct")
        if pos_pct is not None:
            try:
                normalized["position_pct"] = float(pos_pct)
            except Exception:
                pass
        units_val = controls.get("position_pct_units") or controls.get("_position_pct_units")
        units_norm = self._normalize_position_pct_units(units_val)
        if units_norm:
            normalized["position_pct_units"] = units_norm
        leverage = controls.get("leverage")
        if leverage is not None:
            try:
                lev_val = int(leverage)
                if lev_val >= 1:
                    normalized["leverage"] = lev_val
            except Exception:
                pass
        loop_override = self._normalize_loop_override(controls.get("loop_interval_override"))
        if loop_override:
            normalized["loop_interval_override"] = loop_override
        add_only = controls.get("add_only")
        if add_only is not None:
            normalized["add_only"] = bool(add_only)
        account_mode = controls.get("account_mode")
        if account_mode:
            normalized["account_mode"] = self._normalize_account_mode(account_mode)
        stop_loss_raw = controls.get("stop_loss")
        if isinstance(stop_loss_raw, dict):
            normalized["stop_loss"] = shared._normalize_stop_loss(stop_loss_raw)
        backend_val = controls.get("connector_backend")
        if backend_val:
            normalized["connector_backend"] = shared._normalize_connector_backend_value(backend_val)
    elif kind == "backtest":
        logic_raw = str(controls.get("logic") or "").upper()
        if logic_raw in {"AND", "OR", "SEPARATE"}:
            normalized["logic"] = logic_raw
        capital = controls.get("capital")
        if capital is not None:
            try:
                normalized["capital"] = float(capital)
            except Exception:
                pass
        pos_pct = controls.get("position_pct")
        if pos_pct is not None:
            try:
                normalized["position_pct"] = float(pos_pct)
            except Exception:
                pass
        units_val = controls.get("position_pct_units") or controls.get("_position_pct_units")
        units_norm = self._normalize_position_pct_units(units_val)
        if units_norm:
            normalized["position_pct_units"] = units_norm
        side_val = controls.get("side")
        if side_val:
            side_code = str(side_val).upper()
            if side_code not in shared.side_labels():
                side_code = self._canonical_side_from_text(str(side_val))
            if side_code in shared.side_labels():
                normalized["side"] = side_code
        margin_mode = controls.get("margin_mode")
        if margin_mode:
            normalized["margin_mode"] = str(margin_mode)
        position_mode = controls.get("position_mode")
        if position_mode:
            normalized["position_mode"] = str(position_mode)
        assets_mode = controls.get("assets_mode")
        if assets_mode:
            normalized["assets_mode"] = self._normalize_assets_mode(assets_mode)
        account_mode = controls.get("account_mode")
        if account_mode:
            normalized["account_mode"] = self._normalize_account_mode(account_mode)
        loop_override = self._normalize_loop_override(controls.get("loop_interval_override"))
        if loop_override:
            normalized["loop_interval_override"] = loop_override
        leverage = controls.get("leverage")
        if leverage is not None:
            try:
                normalized["leverage"] = int(leverage)
            except Exception:
                pass
        stop_loss_raw = controls.get("stop_loss")
        if isinstance(stop_loss_raw, dict):
            normalized["stop_loss"] = shared._normalize_stop_loss(stop_loss_raw)
        backend_val = controls.get("connector_backend")
        if backend_val:
            normalized["connector_backend"] = shared._normalize_connector_backend_value(backend_val)
    return normalized


def _format_strategy_controls_summary(self, kind: str, controls: dict) -> str:
    if not controls:
        return "-"
    parts: list[str] = []
    if kind == "runtime":
        side = controls.get("side")
        if side:
            parts.append(f"Side={side}")
        pos_pct = controls.get("position_pct")
        if pos_pct is not None:
            try:
                pct_value = float(pos_pct)
                units_norm = self._normalize_position_pct_units(controls.get("position_pct_units"))
                if units_norm == "fraction":
                    pct_value *= 100.0
                parts.append(f"Pos={pct_value:.2f}%")
            except Exception:
                pass
        leverage = controls.get("leverage")
        if leverage is not None:
            try:
                parts.append(f"Lev={int(leverage)}x")
            except Exception:
                pass
        loop = controls.get("loop_interval_override") or "auto"
        parts.append(f"Loop={loop}")
        add_only = controls.get("add_only")
        if add_only is not None:
            parts.append(f"AddOnly={'Y' if add_only else 'N'}")
        account_mode = controls.get("account_mode")
        if account_mode:
            parts.append(f"AcctMode={account_mode}")
        stop_loss = controls.get("stop_loss")
        if isinstance(stop_loss, dict):
            if stop_loss.get("enabled"):
                mode = str(stop_loss.get("mode") or "usdt")
                summary_bits = []
                scope_val = str(stop_loss.get("scope") or "per_trade")
                summary_bits.append(f"scope={scope_val}")
                summary_bits.append(f"mode={mode}")
                if mode == "usdt" and stop_loss.get("usdt"):
                    summary_bits.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                elif mode == "percent" and stop_loss.get("percent"):
                    summary_bits.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                elif mode == "both":
                    if stop_loss.get("usdt") is not None:
                        summary_bits.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                    if stop_loss.get("percent") is not None:
                        summary_bits.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                parts.append(f"SL=On({'; '.join(summary_bits)})")
            else:
                parts.append("SL=Off")
    elif kind == "backtest":
        logic = controls.get("logic")
        if logic:
            parts.append(f"Logic={logic}")
        pos_pct = controls.get("position_pct")
        if pos_pct is not None:
            try:
                pct_value = float(pos_pct)
                units_norm = self._normalize_position_pct_units(controls.get("position_pct_units"))
                if units_norm == "fraction":
                    pct_value *= 100.0
                parts.append(f"Pos={pct_value:.2f}%")
            except Exception:
                pass
        capital = controls.get("capital")
        if capital is not None:
            try:
                parts.append(f"Cap={float(capital):.0f}")
            except Exception:
                pass
        leverage = controls.get("leverage")
        if leverage is not None:
            try:
                parts.append(f"Lev={int(leverage)}")
            except Exception:
                pass
        side = controls.get("side")
        if side:
            parts.append(f"Side={side}")
        margin_mode = controls.get("margin_mode")
        if margin_mode:
            parts.append(f"Margin={margin_mode}")
        assets_mode = controls.get("assets_mode")
        if assets_mode:
            parts.append(f"Assets={assets_mode}")
        account_mode = controls.get("account_mode")
        if account_mode:
            parts.append(f"AcctMode={account_mode}")
        stop_loss = controls.get("stop_loss")
        if isinstance(stop_loss, dict):
            if stop_loss.get("enabled"):
                mode = str(stop_loss.get("mode") or "usdt")
                scope_val = str(stop_loss.get("scope") or "per_trade")
                details = []
                details.append(f"mode={mode}")
                details.append(f"scope={scope_val}")
                if stop_loss.get("usdt") not in (None, ""):
                    details.append(f"U={float(stop_loss.get('usdt', 0.0)):.0f}")
                if stop_loss.get("percent") not in (None, ""):
                    details.append(f"P={float(stop_loss.get('percent', 0.0)):.2f}%")
                parts.append(f"SL=On({'; '.join(details)})")
            else:
                parts.append("SL=Off")
    return ", ".join(parts) if parts else "-"
