from __future__ import annotations

from dataclasses import dataclass

from PyQt6 import QtCore

from .main_window_start_strategy_shared_runtime import _normalize_indicator_keys


@dataclass(slots=True)
class StrategyStartContext:
    account_type_text: str
    default_loop_override: str
    is_futures_account: bool
    pair_entries: list[dict]
    combos: list[dict]


def _collect_strategy_start_context(self) -> StrategyStartContext:
    default_loop_override = self._loop_choice_value(getattr(self, "loop_combo", None))
    account_type_text = (self.account_combo.currentText() or "Futures").strip()
    is_futures_account = account_type_text.upper().startswith("FUT")
    pair_entries = _collect_selected_pair_entries(self, account_type_text)
    if not pair_entries:
        pair_entries = _collect_config_pair_entries(self, account_type_text)
    combos = _build_strategy_combos(self, pair_entries, account_type_text)
    return StrategyStartContext(
        account_type_text=account_type_text,
        default_loop_override=default_loop_override,
        is_futures_account=is_futures_account,
        pair_entries=pair_entries,
        combos=combos,
    )


def _collect_selected_pair_entries(self, account_type_text: str) -> list[dict]:
    pair_entries: list[dict] = []
    runtime_ctx = self._override_ctx("runtime")
    table = runtime_ctx.get("table") if runtime_ctx else None
    if table is None:
        return pair_entries

    try:
        selected_rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
    except Exception:
        selected_rows = []

    for row in selected_rows:
        sym_item = table.item(row, 0)
        iv_item = table.item(row, 1)
        sym = sym_item.text().strip().upper() if sym_item else ""
        iv_raw = iv_item.text().strip() if iv_item else ""
        iv_canonical = self._canonicalize_interval(iv_raw)
        if sym and iv_canonical:
            entry_obj = None
            try:
                entry_obj = sym_item.data(QtCore.Qt.ItemDataRole.UserRole)
            except Exception:
                entry_obj = None

            indicators = None
            controls = None
            if isinstance(entry_obj, dict):
                indicators = _normalize_indicator_keys(entry_obj.get("indicators")) or None
                controls = entry_obj.get("strategy_controls")

            pair_entries.append(
                {
                    "symbol": sym,
                    "interval": iv_canonical,
                    "indicators": list(indicators) if indicators else None,
                    "strategy_controls": self._normalize_strategy_controls(
                        "runtime",
                        controls,
                    ),
                }
            )
            continue

        if sym and iv_raw:
            self.log(f"Skipping unsupported interval '{iv_raw}' for {account_type_text} {sym}.")

    return pair_entries


def _collect_config_pair_entries(self, account_type_text: str) -> list[dict]:
    pair_entries: list[dict] = []
    for entry in self.config.get("runtime_symbol_interval_pairs", []) or []:
        sym = str((entry or {}).get("symbol") or "").strip().upper()
        interval_val = str((entry or {}).get("interval") or "").strip()
        iv_canonical = self._canonicalize_interval(interval_val)
        if not (sym and iv_canonical):
            if sym and interval_val:
                self.log(
                    f"Skipping unsupported interval '{interval_val}' for {account_type_text} {sym}."
                )
            continue

        indicators = _normalize_indicator_keys(entry.get("indicators")) or None
        controls = self._normalize_strategy_controls("runtime", entry.get("strategy_controls"))
        pair_entries.append(
            {
                "symbol": sym,
                "interval": iv_canonical,
                "indicators": list(indicators) if indicators else None,
                "strategy_controls": controls,
            }
        )

    return pair_entries


def _build_strategy_combos(self, pair_entries: list[dict], account_type_text: str) -> list[dict]:
    combos_map: dict[tuple[str, str], dict] = {}

    for entry in pair_entries:
        sym = str(entry.get("symbol") or "").strip().upper()
        iv_raw = str(entry.get("interval") or "").strip()
        iv = self._canonicalize_interval(iv_raw)
        if not sym or not iv:
            if sym and iv_raw:
                self.log(f"Skipping unsupported interval '{iv_raw}' for {account_type_text} {sym}.")
            continue

        indicators = _normalize_indicator_keys(entry.get("indicators"))
        controls = entry.get("strategy_controls")
        combo_key = (sym, iv)
        combo_entry = combos_map.setdefault(
            combo_key,
            {
                "symbol": sym,
                "interval": iv,
                "indicators": [],
                "strategy_controls": {},
            },
        )
        if indicators:
            try:
                indicator_set = set(combo_entry.get("indicators") or [])
                indicator_set.update(indicators)
                combo_entry["indicators"] = sorted(indicator_set)
            except Exception:
                combo_entry["indicators"] = list(indicators)
        if isinstance(controls, dict):
            try:
                strategy_controls = combo_entry.setdefault("strategy_controls", {})
                for key_name, value in controls.items():
                    if value is not None:
                        strategy_controls[key_name] = value
            except Exception:
                combo_entry["strategy_controls"] = controls

    return list(combos_map.values())
