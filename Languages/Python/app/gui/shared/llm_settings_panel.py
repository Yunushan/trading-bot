from __future__ import annotations

import json
from collections.abc import Callable

from PyQt6 import QtCore, QtGui, QtWidgets

from ...integrations.llm.local_models import (
    OLLAMA_DOWNLOAD_URL,
    delete_ollama_model,
    estimate_ollama_model_size_label,
    get_local_model_status,
    ollama_model_storage_hint,
    pull_ollama_model,
    start_ollama_server,
)
from ...integrations.llm.discovery import discover_llm_models
from ...integrations.llm.providers import (
    LLM_API_STYLE_OPTIONS,
    LLM_SPEED_OPTIONS,
    build_llm_config_payload,
    list_llm_provider_specs,
)

_USE_FOR_OPTIONS = (
    ("Advisory", "advisory"),
    ("Signal confirmation", "signal_confirmation"),
    ("Risk review", "risk_review"),
    ("Backtest explanation", "backtest_explanation"),
)


class _LocalModelDownloadWorker(QtCore.QObject):
    progress = QtCore.pyqtSignal(str)
    finished = QtCore.pyqtSignal(str, str)

    def __init__(self, base_url: str, model: str, puller: Callable[..., None]) -> None:
        super().__init__()
        self._base_url = base_url
        self._model = model
        self._puller = puller
        self._cancel_requested = False

    def _emit_progress(self, payload: dict[str, object]) -> None:
        status = str(payload.get("status") or "").strip()
        completed = payload.get("completed")
        total = payload.get("total")
        detail = status or "downloading"
        try:
            completed_float = float(completed)
            total_float = float(total)
            if total_float > 0:
                percent = max(0.0, min(100.0, completed_float / total_float * 100.0))
                detail = f"{detail} ({percent:.0f}%)"
        except (TypeError, ValueError):
            pass
        self.progress.emit(f"Downloading local model '{self._model}' with Ollama: {detail}")

    @QtCore.pyqtSlot()
    def cancel(self) -> None:
        self._cancel_requested = True
        self.progress.emit(f"Cancelling local model '{self._model}' download...")

    def _is_cancelled(self) -> bool:
        return bool(getattr(self, "_cancel_requested", False))

    @QtCore.pyqtSlot()
    def run(self) -> None:
        error = ""
        try:
            self._cancel_requested = False
            self._puller(
                self._base_url,
                self._model,
                progress_callback=self._emit_progress,
                cancel_callback=self._is_cancelled,
            )
        except Exception as exc:
            error = str(exc)
        self.finished.emit(self._model, error)


class _ModelDiscoveryWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(object)

    def __init__(self, config: dict[str, object]) -> None:
        super().__init__()
        self._config = dict(config)

    @QtCore.pyqtSlot()
    def run(self) -> None:
        self.finished.emit(discover_llm_models(self._config))


class LLMSettingsPanel(QtWidgets.QGroupBox):
    def __init__(
        self,
        config: dict,
        *,
        title: str = "AI / LLM Settings",
        parent: QtWidgets.QWidget | None = None,
        on_apply: Callable[["LLMSettingsPanel"], None] | None = None,
    ) -> None:
        super().__init__(title, parent)
        self._config = config
        self._on_apply = on_apply
        self._provider_specs = list_llm_provider_specs()
        self._provider_by_key = {
            str(item.get("key") or ""): item for item in self._provider_specs
        }
        self._refreshing = False
        self._local_model_download_thread: QtCore.QThread | None = None
        self._local_model_download_worker: _LocalModelDownloadWorker | None = None
        self._local_model_download_restore_apply_enabled = True
        self._model_discovery_thread: QtCore.QThread | None = None
        self._model_discovery_worker: _ModelDiscoveryWorker | None = None
        self._discovered_models_by_id: dict[str, dict[str, object]] = {}
        self._build_ui()
        self.refresh_from_config()

    def runtime_lock_widgets(self) -> list[QtWidgets.QWidget]:
        return [self]

    def refresh_from_config(self) -> None:
        self._refreshing = True
        try:
            payload = build_llm_config_payload(self._config)
            allow_public_network = bool(payload.get("allow_public_network"))
            provider_key = self._coerce_provider_for_network(
                str(payload.get("provider") or "openai"),
                allow_public_network,
            )
            if provider_key != str(payload.get("provider") or ""):
                payload = build_llm_config_payload(
                    {
                        **self._config,
                        "llm_provider": provider_key,
                        "llm_allow_public_network": allow_public_network,
                    }
                )
            provider_idx = self.provider_combo.findData(provider_key)
            if provider_idx < 0:
                provider_idx = 0
            self.allow_public_network_check.setChecked(allow_public_network)
            self._sync_provider_access(allow_public_network)
            self.provider_combo.setCurrentIndex(provider_idx)
            self._sync_local_model_action_visibility(provider_key)
            self.enabled_check.setChecked(bool(payload.get("enabled")))
            self._refresh_models_for_provider(provider_key, str(payload.get("model") or ""))
            self._refresh_reasoning_for_provider(provider_key, str(payload.get("reasoning_effort") or ""))
            self._refresh_api_styles_for_provider(provider_key, str(payload.get("api_style") or "provider-default"))
            self._refresh_speed_for_provider(provider_key, str(payload.get("speed") or "default"))
            self.base_url_edit.setText(str(payload.get("base_url") or ""))
            self.api_key_env_edit.setText(str(payload.get("api_key_env") or ""))
            self.api_key_edit.setText("********" if payload.get("api_key_present") else "")
            use_for = str(payload.get("use_for") or "advisory")
            use_idx = self.use_for_combo.findData(use_for)
            self.use_for_combo.setCurrentIndex(use_idx if use_idx >= 0 else 0)
            self.context_window_spin.setValue(int(payload.get("context_window") or 0))
            self.max_output_tokens_spin.setValue(int(payload.get("max_output_tokens") or 0))
            self.verbosity_combo.setCurrentText(str(payload.get("verbosity") or "default"))
            self.temperature_spin.setValue(
                float(payload["temperature"]) if payload.get("temperature") is not None else -1.0
            )
            self.top_p_spin.setValue(float(payload["top_p"]) if payload.get("top_p") is not None else -1.0)
            self.timeout_spin.setValue(int(payload.get("timeout_seconds") or 30))
            self.request_options_edit.setPlainText(
                json.dumps(payload.get("request_options") or {}, ensure_ascii=False, sort_keys=True)
            )
            self._set_status(payload)
            self._set_dependent_controls_enabled(bool(payload.get("enabled")))
        finally:
            self._refreshing = False

    def apply_to_config(self) -> None:
        provider_key = str(self.provider_combo.currentData() or "openai")
        provider = self._provider_by_key.get(provider_key) or {}
        model = str(self.model_combo.currentText() or "").strip()
        base_url = str(self.base_url_edit.text() or "").strip()
        api_key_env = str(self.api_key_env_edit.text() or "").strip()
        api_key = str(self.api_key_edit.text() or "").strip()
        request_options = self._request_options_from_editor(show_error=True)
        if request_options is None:
            return

        enabled = bool(self.enabled_check.isChecked())
        if not self._ensure_local_model_available(
            provider_key=provider_key,
            enabled=enabled,
            base_url=base_url or str(provider.get("default_base_url") or ""),
            model=model or str(provider.get("default_model") or ""),
            show_installed_message=False,
        ):
            return

        self._config["llm_enabled"] = enabled
        self._config["llm_provider"] = provider_key
        self._config["llm_model"] = model or str(provider.get("default_model") or "")
        self._config["llm_base_url"] = base_url or str(provider.get("default_base_url") or "")
        self._config["llm_api_key_env"] = api_key_env or str(provider.get("api_key_env") or "")
        self._config["llm_use_for"] = str(self.use_for_combo.currentData() or "advisory")
        self._config["llm_allow_public_network"] = bool(self.allow_public_network_check.isChecked())
        self._config["llm_api_style"] = str(self.api_style_combo.currentText() or "provider-default").strip()
        self._config["llm_reasoning_effort"] = str(self.reasoning_combo.currentText() or "default").strip()
        self._config["llm_speed"] = str(self.speed_combo.currentText() or "default").strip()
        self._config["llm_context_window"] = int(self.context_window_spin.value())
        self._config["llm_max_output_tokens"] = int(self.max_output_tokens_spin.value())
        self._config["llm_verbosity"] = str(self.verbosity_combo.currentText() or "default").strip()
        self._config["llm_temperature"] = None if self.temperature_spin.value() < 0 else float(self.temperature_spin.value())
        self._config["llm_top_p"] = None if self.top_p_spin.value() < 0 else float(self.top_p_spin.value())
        self._config["llm_timeout_seconds"] = int(self.timeout_spin.value())
        self._config["llm_request_options"] = request_options
        if api_key and api_key != "********":
            self._config["llm_api_key"] = api_key

        self.refresh_from_config()
        if callable(self._on_apply):
            self._on_apply(self)

    def _local_model_status(self, base_url: str, model: str):
        return get_local_model_status(base_url, model)

    def _pull_local_model(self, base_url: str, model: str, *, progress_callback=None, cancel_callback=None) -> None:
        pull_ollama_model(base_url, model, progress_callback=progress_callback, cancel_callback=cancel_callback)

    def _delete_local_model(self, base_url: str, model: str) -> None:
        delete_ollama_model(base_url, model)

    def _start_local_model_server(self, base_url: str):
        return start_ollama_server(base_url)

    def _open_ollama_download(self) -> None:
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(OLLAMA_DOWNLOAD_URL))

    def _ensure_local_model_available(
        self,
        *,
        provider_key: str,
        enabled: bool,
        base_url: str,
        model: str,
        show_installed_message: bool,
    ) -> bool:
        if not self._provider_supports_local_model_actions(provider_key) or not enabled:
            return True
        clean_model = str(model or "").strip()
        if not clean_model or clean_model == "custom-model":
            return True

        status = self._local_model_status(base_url, clean_model)
        if status.installed:
            if show_installed_message:
                QtWidgets.QMessageBox.information(
                    self,
                    "Local model ready",
                    f"The local model '{clean_model}' is already installed and ready.",
                )
            return True
        if status.error:
            if not self._handle_unreachable_local_model_server(base_url, clean_model, status):
                return False
            status = self._wait_for_local_model_server(base_url, clean_model)
            if status.installed:
                if show_installed_message:
                    QtWidgets.QMessageBox.information(
                        self,
                        "Local model ready",
                        f"The local model '{clean_model}' is already installed and ready.",
                    )
                return True
            if status.error:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Local model unavailable",
                    (
                        f"Could not reach the local model server at {base_url}.\n\n"
                        "Start Ollama or your local OpenAI-compatible server, then try again.\n\n"
                        f"Error: {status.error}"
                    ),
                )
                return False
            if not status.can_download:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Local model not found",
                    (
                        f"The selected model '{clean_model}' is not available on the local server at {base_url}.\n\n"
                        "Install or load the model in your local model manager, then try again."
                    ),
                )
                return False
        if not status.can_download:
            QtWidgets.QMessageBox.warning(
                self,
                "Local model not found",
                (
                    f"The selected model '{clean_model}' is not available on the local server at {base_url}.\n\n"
                    "This server does not support automatic downloads from this app. Install or load the model in "
                    "your local model manager, then apply these settings again."
                ),
            )
            return False

        return self._download_local_model(base_url, clean_model, status=status)

    def _handle_unreachable_local_model_server(self, base_url: str, model: str, status) -> bool:
        if status.server_kind != "ollama":
            QtWidgets.QMessageBox.warning(
                self,
                "Local model unavailable",
                (
                    f"Could not check the local model server at {base_url}.\n\n"
                    "Start your local OpenAI-compatible server, then apply these settings again.\n\n"
                    f"Error: {status.error}"
                ),
            )
            return False

        if not status.can_start:
            choice = QtWidgets.QMessageBox.question(
                self,
                "Install Ollama?",
                (
                    "Ollama is not running, and the app could not find the ollama command on this PC.\n\n"
                    "Open the Ollama download page now? After installing Ollama, return here and use "
                    "Check / Download Local Model."
                ),
                QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.Yes,
            )
            if choice == QtWidgets.QMessageBox.StandardButton.Yes:
                self._open_ollama_download()
            self.status_label.setText("Install Ollama, then download the selected local model.")
            return False

        choice = QtWidgets.QMessageBox.question(
            self,
            "Start Ollama?",
            (
                "Ollama is installed but not running.\n\n"
                f"Start Ollama now, then download or use '{model}' on this PC?"
            ),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.Yes,
        )
        if choice != QtWidgets.QMessageBox.StandardButton.Yes:
            self.status_label.setText("Ollama is not running.")
            return False

        self.status_label.setText("Starting Ollama local model server...")
        QtWidgets.QApplication.processEvents()
        result = self._start_local_model_server(base_url)
        if not result.started:
            QtWidgets.QMessageBox.warning(
                self,
                "Ollama startup failed",
                f"Could not start Ollama automatically.\n\nError: {result.error}",
            )
            return False
        return True

    def _wait_for_local_model_server(self, base_url: str, model: str):
        status = self._local_model_status(base_url, model)
        for _ in range(10):
            if not status.error:
                return status
            QtWidgets.QApplication.processEvents()
            QtCore.QThread.msleep(500)
            status = self._local_model_status(base_url, model)
        return status

    def _download_local_model(self, base_url: str, clean_model: str, *, status=None) -> bool:
        disk_warning = str(getattr(status, "disk_space_warning", "") or "").strip()
        disk_text = f"\nWarning: {disk_warning}" if disk_warning else ""
        storage_paths = tuple(getattr(status, "storage_paths", ()) or ())
        storage_text = "; ".join(storage_paths) if storage_paths else ollama_model_storage_hint()
        free_disk = getattr(status, "free_disk_gb", None)
        free_disk_text = f"\nFree disk near model cache: {free_disk:.1f} GB." if isinstance(free_disk, float) else ""
        choice = QtWidgets.QMessageBox.question(
            self,
            "Download local model?",
            (
                f"The local model '{clean_model}' is not installed on this PC.\n\n"
                "The app can ask Ollama to download it now and then use it locally on your computer. "
                f"Estimated size: {estimate_ollama_model_size_label(clean_model)}.\n"
                f"Storage path: {storage_text}{free_disk_text}{disk_text}\n\n"
                "Download now?"
            ),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if choice != QtWidgets.QMessageBox.StandardButton.Yes:
            self.status_label.setText(f"Local model '{clean_model}' is not installed.")
            return False

        self._start_local_model_download(base_url, clean_model)
        return False

    def _start_local_model_download(self, base_url: str, clean_model: str) -> None:
        thread = self._local_model_download_thread
        if thread is not None and thread.isRunning():
            self.status_label.setText("Local model download is already running.")
            return
        self._local_model_download_restore_apply_enabled = self.apply_btn.isEnabled()
        self.apply_btn.setEnabled(False)
        self.local_model_btn.setText("Cancel Download")
        self.local_model_btn.setEnabled(True)
        remove_btn = getattr(self, "remove_local_model_btn", None)
        if remove_btn is not None:
            remove_btn.setEnabled(False)
        self.status_label.setText(
            f"Downloading local model '{clean_model}' with Ollama in the background..."
        )
        worker = _LocalModelDownloadWorker(base_url, clean_model, self._pull_local_model)
        thread = QtCore.QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_local_model_download_progress)
        worker.finished.connect(self._on_local_model_download_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._local_model_download_thread = thread
        self._local_model_download_worker = worker
        thread.start()

    def _on_local_model_download_progress(self, message: str) -> None:
        self.status_label.setText(str(message or "").strip() or "Downloading local model with Ollama...")

    def _on_local_model_download_finished(self, clean_model: str, error: str) -> None:
        try:
            self.apply_btn.setEnabled(bool(self._local_model_download_restore_apply_enabled))
            self.local_model_btn.setEnabled(True)
            self.local_model_btn.setText("Check / Download Local Model")
            remove_btn = getattr(self, "remove_local_model_btn", None)
            if remove_btn is not None:
                remove_btn.setEnabled(True)
        except Exception:
            pass
        self._local_model_download_thread = None
        self._local_model_download_worker = None
        if error:
            if "cancelled" in str(error).lower():
                self.status_label.setText(f"Local model '{clean_model}' download cancelled.")
                return
            QtWidgets.QMessageBox.warning(
                self,
                "Local model download failed",
                (
                    f"Ollama could not download '{clean_model}'.\n\n"
                    "Make sure Ollama is installed and running, then try again.\n\n"
                    f"Error: {error}"
                ),
            )
            self.status_label.setText(f"Local model '{clean_model}' download failed.")
            return

        self.status_label.setText(f"Local model '{clean_model}' is installed and ready.")

    def _on_local_model_action_clicked(self) -> None:
        thread = self._local_model_download_thread
        worker = self._local_model_download_worker
        if thread is not None and thread.isRunning() and worker is not None:
            worker.cancel()
            self.local_model_btn.setEnabled(False)
            self.local_model_btn.setText("Cancelling Download...")
            return

        provider_key = str(self.provider_combo.currentData() or "openai")
        provider = self._provider_by_key.get(provider_key) or {}
        model = str(self.model_combo.currentText() or provider.get("default_model") or "").strip()
        base_url = str(self.base_url_edit.text() or provider.get("default_base_url") or "").strip()
        if not self._provider_supports_local_model_actions(provider_key):
            QtWidgets.QMessageBox.information(
                self,
                "Provider selected",
                "Local model checks are available for local or open-source OpenAI-compatible providers.",
            )
            return
        self._ensure_local_model_available(
            provider_key=provider_key,
            enabled=True,
            base_url=base_url,
            model=model,
            show_installed_message=True,
        )

    def _on_remove_local_model_clicked(self) -> None:
        provider_key = str(self.provider_combo.currentData() or "openai")
        provider = self._provider_by_key.get(provider_key) or {}
        model = str(self.model_combo.currentText() or provider.get("default_model") or "").strip()
        base_url = str(self.base_url_edit.text() or provider.get("default_base_url") or "").strip()
        if not self._provider_supports_local_model_actions(provider_key):
            QtWidgets.QMessageBox.information(
                self,
                "Provider selected",
                "Local model removal is available only for local or open-source OpenAI-compatible providers.",
            )
            return
        if not model or model == "custom-model":
            QtWidgets.QMessageBox.warning(
                self,
                "No removable local model selected",
                "Select a concrete Ollama model before removing it from this PC.",
            )
            return

        status = self._local_model_status(base_url, model)
        if status.error:
            if not self._handle_unreachable_local_model_server(base_url, model, status):
                return
            status = self._wait_for_local_model_server(base_url, model)
            if status.error:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Local model unavailable",
                    (
                        f"Could not reach the local model server at {base_url}.\n\n"
                        "Start Ollama, then try removing the model again.\n\n"
                        f"Error: {status.error}"
                    ),
                )
                return
        if status.server_kind != "ollama":
            QtWidgets.QMessageBox.warning(
                self,
                "Cannot remove local model automatically",
                "Automatic local model removal is only supported for Ollama on localhost:11434.",
            )
            return
        if not status.installed:
            QtWidgets.QMessageBox.information(
                self,
                "Local model not installed",
                f"The local model '{model}' is not installed in Ollama on this PC.",
            )
            return

        storage_paths = tuple(getattr(status, "storage_paths", ()) or ())
        storage_text = "; ".join(storage_paths) if storage_paths else ollama_model_storage_hint()
        choice = QtWidgets.QMessageBox.question(
            self,
            "Remove local model?",
            (
                f"Remove '{model}' from this PC's Ollama model cache?\n\n"
                f"Storage path: {storage_text}\n\n"
                "This only removes the local downloaded model files. It does not change project files."
            ),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No,
        )
        if choice != QtWidgets.QMessageBox.StandardButton.Yes:
            self.status_label.setText(f"Local model '{model}' was not removed.")
            return

        try:
            self._delete_local_model(base_url, model)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(
                self,
                "Local model removal failed",
                f"Ollama could not remove '{model}'.\n\nError: {exc}",
            )
            self.status_label.setText(f"Local model '{model}' removal failed.")
            return
        self.status_label.setText(f"Local model '{model}' was removed from this PC.")

    def _build_ui(self) -> None:
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(10, 14, 10, 10)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        self.enabled_check = QtWidgets.QCheckBox("Enable LLM assistance", self)
        layout.addWidget(self.enabled_check, 0, 0, 1, 2)

        self.allow_public_network_check = QtWidgets.QCheckBox("Allow public network endpoint", self)
        self.allow_public_network_check.setToolTip(
            "Keep this unchecked for local/private IP endpoints. Enable it for cloud providers."
        )
        layout.addWidget(self.allow_public_network_check, 0, 2, 1, 2)

        self.provider_label = QtWidgets.QLabel("Provider:", self)
        layout.addWidget(self.provider_label, 1, 0)
        self.provider_combo = QtWidgets.QComboBox(self)
        for provider in self._provider_specs:
            self.provider_combo.addItem(
                str(provider.get("label") or provider.get("key") or ""),
                str(provider.get("key") or ""),
            )
        layout.addWidget(self.provider_combo, 1, 1)

        self.model_label = QtWidgets.QLabel("Model:", self)
        layout.addWidget(self.model_label, 1, 2)
        self.model_combo = QtWidgets.QComboBox(self)
        self.model_combo.setEditable(True)
        self.model_combo.setInsertPolicy(QtWidgets.QComboBox.InsertPolicy.NoInsert)
        layout.addWidget(self.model_combo, 1, 3)
        self.refresh_models_btn = QtWidgets.QPushButton("Refresh Models", self)
        self.refresh_models_btn.setToolTip("Merge the provider's live /models response with catalog, custom, and historical IDs.")
        layout.addWidget(self.refresh_models_btn, 1, 4)

        self.base_url_label = QtWidgets.QLabel("Base URL / IP:", self)
        layout.addWidget(self.base_url_label, 2, 0)
        self.base_url_edit = QtWidgets.QLineEdit(self)
        self.base_url_edit.setPlaceholderText("https://api.openai.com/v1 or http://192.168.1.20:11434/v1")
        layout.addWidget(self.base_url_edit, 2, 1, 1, 3)

        self.api_key_env_label = QtWidgets.QLabel("API key env:", self)
        layout.addWidget(self.api_key_env_label, 3, 0)
        self.api_key_env_edit = QtWidgets.QLineEdit(self)
        self.api_key_env_edit.setPlaceholderText("OPENAI_API_KEY")
        layout.addWidget(self.api_key_env_edit, 3, 1)

        self.api_key_label = QtWidgets.QLabel("API token:", self)
        layout.addWidget(self.api_key_label, 3, 2)
        self.api_key_edit = QtWidgets.QLineEdit(self)
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("Optional; env var is preferred")
        layout.addWidget(self.api_key_edit, 3, 3)

        self.use_for_label = QtWidgets.QLabel("Use for:", self)
        layout.addWidget(self.use_for_label, 4, 0)
        self.use_for_combo = QtWidgets.QComboBox(self)
        for label, value in _USE_FOR_OPTIONS:
            self.use_for_combo.addItem(label, value)
        layout.addWidget(self.use_for_combo, 4, 1)

        self.reasoning_label = QtWidgets.QLabel("Reasoning / Thinking:", self)
        layout.addWidget(self.reasoning_label, 4, 2)
        self.reasoning_combo = QtWidgets.QComboBox(self)
        self.reasoning_combo.setEditable(True)
        layout.addWidget(self.reasoning_combo, 4, 3)

        self.api_style_label = QtWidgets.QLabel("API style:", self)
        layout.addWidget(self.api_style_label, 5, 0)
        self.api_style_combo = QtWidgets.QComboBox(self)
        self.api_style_combo.setEditable(True)
        layout.addWidget(self.api_style_combo, 5, 1)

        self.speed_label = QtWidgets.QLabel("Speed / service tier:", self)
        layout.addWidget(self.speed_label, 5, 2)
        self.speed_combo = QtWidgets.QComboBox(self)
        self.speed_combo.setEditable(True)
        layout.addWidget(self.speed_combo, 5, 3)

        self.context_window_label = QtWidgets.QLabel("Context window:", self)
        layout.addWidget(self.context_window_label, 6, 0)
        self.context_window_spin = QtWidgets.QSpinBox(self)
        self.context_window_spin.setRange(0, 10_000_000)
        self.context_window_spin.setSpecialValueText("Auto / model default")
        self.context_window_spin.setSingleStep(1024)
        layout.addWidget(self.context_window_spin, 6, 1)

        self.max_output_tokens_label = QtWidgets.QLabel("Max output tokens:", self)
        layout.addWidget(self.max_output_tokens_label, 6, 2)
        self.max_output_tokens_spin = QtWidgets.QSpinBox(self)
        self.max_output_tokens_spin.setRange(0, 2_000_000)
        self.max_output_tokens_spin.setSpecialValueText("Provider default")
        self.max_output_tokens_spin.setSingleStep(256)
        layout.addWidget(self.max_output_tokens_spin, 6, 3)

        self.verbosity_label = QtWidgets.QLabel("Verbosity:", self)
        layout.addWidget(self.verbosity_label, 7, 0)
        self.verbosity_combo = QtWidgets.QComboBox(self)
        self.verbosity_combo.setEditable(True)
        self.verbosity_combo.addItems(["default", "low", "medium", "high"])
        layout.addWidget(self.verbosity_combo, 7, 1)

        self.timeout_label = QtWidgets.QLabel("Timeout seconds:", self)
        layout.addWidget(self.timeout_label, 7, 2)
        self.timeout_spin = QtWidgets.QSpinBox(self)
        self.timeout_spin.setRange(1, 3600)
        self.timeout_spin.setValue(30)
        layout.addWidget(self.timeout_spin, 7, 3)

        self.temperature_label = QtWidgets.QLabel("Temperature:", self)
        layout.addWidget(self.temperature_label, 8, 0)
        self.temperature_spin = QtWidgets.QDoubleSpinBox(self)
        self.temperature_spin.setRange(-1.0, 2.0)
        self.temperature_spin.setDecimals(2)
        self.temperature_spin.setSingleStep(0.05)
        self.temperature_spin.setSpecialValueText("Provider default")
        self.temperature_spin.setValue(-1.0)
        layout.addWidget(self.temperature_spin, 8, 1)

        self.top_p_label = QtWidgets.QLabel("Top P:", self)
        layout.addWidget(self.top_p_label, 8, 2)
        self.top_p_spin = QtWidgets.QDoubleSpinBox(self)
        self.top_p_spin.setRange(-1.0, 1.0)
        self.top_p_spin.setDecimals(2)
        self.top_p_spin.setSingleStep(0.05)
        self.top_p_spin.setSpecialValueText("Provider default")
        self.top_p_spin.setValue(-1.0)
        layout.addWidget(self.top_p_spin, 8, 3)

        self.request_options_label = QtWidgets.QLabel("Advanced request JSON:", self)
        layout.addWidget(self.request_options_label, 9, 0)
        self.request_options_edit = QtWidgets.QPlainTextEdit(self)
        self.request_options_edit.setPlaceholderText('{"seed": 42, "response_format": {"type": "json_object"}}')
        self.request_options_edit.setMaximumHeight(64)
        self.request_options_edit.setToolTip(
            "Provider-specific JSON options. Model, prompts, tools, streaming, and advisory-boundary fields are protected."
        )
        layout.addWidget(self.request_options_edit, 9, 1, 1, 4)

        self.apply_btn = QtWidgets.QPushButton("Apply LLM Settings", self)
        layout.addWidget(self.apply_btn, 10, 2)
        self.local_model_btn = QtWidgets.QPushButton("Check / Download Local Model", self)
        layout.addWidget(self.local_model_btn, 10, 1)
        self.remove_local_model_btn = QtWidgets.QPushButton("Remove Local Model", self)
        layout.addWidget(self.remove_local_model_btn, 11, 1)

        self.status_label = QtWidgets.QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #94a3b8; font-weight: 600;")
        layout.addWidget(self.status_label, 10, 3, 2, 2)

        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 2)

        self._dependent_widgets = [
            self.allow_public_network_check,
            self.provider_label,
            self.provider_combo,
            self.model_label,
            self.model_combo,
            self.refresh_models_btn,
            self.base_url_label,
            self.base_url_edit,
            self.api_key_env_label,
            self.api_key_env_edit,
            self.api_key_label,
            self.api_key_edit,
            self.use_for_label,
            self.use_for_combo,
            self.reasoning_label,
            self.reasoning_combo,
            self.api_style_label,
            self.api_style_combo,
            self.speed_label,
            self.speed_combo,
            self.context_window_label,
            self.context_window_spin,
            self.max_output_tokens_label,
            self.max_output_tokens_spin,
            self.verbosity_label,
            self.verbosity_combo,
            self.timeout_label,
            self.timeout_spin,
            self.temperature_label,
            self.temperature_spin,
            self.top_p_label,
            self.top_p_spin,
            self.request_options_label,
            self.request_options_edit,
            self.local_model_btn,
            self.remove_local_model_btn,
        ]

        self.enabled_check.toggled.connect(self._on_enabled_toggled)
        self.allow_public_network_check.toggled.connect(self._on_allow_public_network_toggled)
        self.provider_combo.currentIndexChanged.connect(self._on_provider_changed)
        self.reasoning_combo.currentIndexChanged.connect(self._on_reasoning_changed)
        self.api_style_combo.currentIndexChanged.connect(self._on_reasoning_changed)
        self.speed_combo.currentIndexChanged.connect(self._on_reasoning_changed)
        self.refresh_models_btn.clicked.connect(self._on_refresh_models_clicked)
        self.apply_btn.clicked.connect(self.apply_to_config)
        self.local_model_btn.clicked.connect(self._on_local_model_action_clicked)
        self.remove_local_model_btn.clicked.connect(self._on_remove_local_model_clicked)
        self._sync_local_model_action_visibility("openai")

    def _on_enabled_toggled(self, checked: bool) -> None:
        self._set_dependent_controls_enabled(bool(checked))
        if self._refreshing:
            return
        payload = build_llm_config_payload({**self._config, "llm_enabled": bool(checked)})
        self._set_status(payload)

    def _on_allow_public_network_toggled(self, checked: bool) -> None:
        self._sync_provider_access(bool(checked))
        if self._refreshing:
            return
        provider_key = str(self.provider_combo.currentData() or "openai")
        if not self._provider_allowed(provider_key, bool(checked)):
            self._select_provider_key(self._fallback_provider_key(), block_signals=False)
            return
        self._set_status(self._current_payload_from_widgets())

    def _set_dependent_controls_enabled(self, enabled: bool) -> None:
        for widget in self._dependent_widgets:
            widget.setEnabled(enabled)
            if enabled:
                widget.setGraphicsEffect(None)
                continue
            effect = QtWidgets.QGraphicsOpacityEffect(widget)
            effect.setOpacity(0.42)
            widget.setGraphicsEffect(effect)

    def _on_provider_changed(self) -> None:
        if self._refreshing:
            return
        provider_key = str(self.provider_combo.currentData() or "openai")
        if not self._provider_allowed(provider_key, bool(self.allow_public_network_check.isChecked())):
            self._select_provider_key(self._fallback_provider_key(), block_signals=False)
            return
        self._refresh_models_for_provider(provider_key, "")
        self._refresh_reasoning_for_provider(provider_key, "")
        self._refresh_api_styles_for_provider(provider_key, "provider-default")
        self._refresh_speed_for_provider(provider_key, "default")
        self._sync_local_model_action_visibility(provider_key)
        provider = self._provider_by_key.get(provider_key) or {}
        self.base_url_edit.setText(str(provider.get("default_base_url") or ""))
        self.api_key_env_edit.setText(str(provider.get("api_key_env") or ""))
        self.allow_public_network_check.setChecked(str(provider.get("mode") or "") == "cloud")
        self._set_status(self._current_payload_from_widgets())

    def _on_reasoning_changed(self) -> None:
        if self._refreshing:
            return
        self._set_status(self._current_payload_from_widgets())

    def _provider_allowed(self, provider_key: str, allow_public_network: bool) -> bool:
        provider = self._provider_by_key.get(provider_key) or {}
        return bool(allow_public_network) or str(provider.get("mode") or "") != "cloud"

    def _fallback_provider_key(self) -> str:
        for provider in self._provider_specs:
            if str(provider.get("mode") or "") != "cloud":
                return str(provider.get("key") or "local")
        return str(self._provider_specs[0].get("key") or "openai") if self._provider_specs else "openai"

    def _coerce_provider_for_network(self, provider_key: str, allow_public_network: bool) -> str:
        if self._provider_allowed(provider_key, allow_public_network):
            return provider_key
        return self._fallback_provider_key()

    def _select_provider_key(self, provider_key: str, *, block_signals: bool) -> None:
        idx = self.provider_combo.findData(provider_key)
        if idx < 0:
            idx = 0
        if block_signals:
            with QtCore.QSignalBlocker(self.provider_combo):
                self.provider_combo.setCurrentIndex(idx)
        else:
            self.provider_combo.setCurrentIndex(idx)
        self._sync_local_model_action_visibility(str(self.provider_combo.itemData(idx) or ""))

    def _sync_provider_access(self, allow_public_network: bool) -> None:
        model = self.provider_combo.model()
        for idx in range(self.provider_combo.count()):
            provider_key = str(self.provider_combo.itemData(idx) or "")
            allowed = self._provider_allowed(provider_key, allow_public_network)
            item = model.item(idx) if hasattr(model, "item") else None
            if item is None:
                continue
            item.setEnabled(allowed)
            item.setForeground(QtGui.QColor("#f8fafc" if allowed else "#64748b"))
        current_key = str(self.provider_combo.currentData() or "")
        if current_key and not self._provider_allowed(current_key, allow_public_network):
            self._select_provider_key(self._fallback_provider_key(), block_signals=self._refreshing)

    def _sync_local_model_action_visibility(self, provider_key: str) -> None:
        local = self._provider_supports_local_model_actions(provider_key)
        for name in ("local_model_btn", "remove_local_model_btn"):
            btn = getattr(self, name, None)
            if btn is not None:
                btn.setVisible(local)

    def _provider_supports_local_model_actions(self, provider_key: str) -> bool:
        provider = self._provider_by_key.get(str(provider_key or "")) or {}
        return str(provider.get("mode") or "") == "local"

    def _on_refresh_models_clicked(self) -> None:
        thread = self._model_discovery_thread
        if thread is not None and thread.isRunning():
            self.status_label.setText("Model discovery is already running.")
            return
        self.refresh_models_btn.setEnabled(False)
        self.refresh_models_btn.setText("Refreshing...")
        self.status_label.setText("Discovering live models and preserving catalog/custom IDs...")
        worker = _ModelDiscoveryWorker(self._current_config_from_widgets())
        thread = QtCore.QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_model_discovery_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._model_discovery_thread = thread
        self._model_discovery_worker = worker
        thread.start()

    def _on_model_discovery_finished(self, result: object) -> None:
        self._model_discovery_thread = None
        self._model_discovery_worker = None
        self.refresh_models_btn.setEnabled(bool(self.enabled_check.isChecked()))
        self.refresh_models_btn.setText("Refresh Models")
        payload = result if isinstance(result, dict) else {}
        models = payload.get("models") if isinstance(payload.get("models"), list) else []
        current_model = str(self.model_combo.currentText() or "").strip()
        self._discovered_models_by_id = {
            str(record.get("id") or ""): dict(record)
            for record in models
            if isinstance(record, dict) and str(record.get("id") or "").strip()
        }
        suggestions = list(self._discovered_models_by_id)
        if current_model and current_model not in suggestions:
            suggestions.insert(0, current_model)
        with QtCore.QSignalBlocker(self.model_combo):
            self.model_combo.clear()
            self.model_combo.addItems(suggestions)
            self.model_combo.setCurrentText(current_model or (suggestions[0] if suggestions else ""))
        selected = self._discovered_models_by_id.get(str(self.model_combo.currentText() or "")) or {}
        if self.context_window_spin.value() == 0 and selected.get("context_window"):
            self.context_window_spin.setValue(int(selected["context_window"]))
        if self.max_output_tokens_spin.value() == 0 and selected.get("max_output_tokens"):
            self.max_output_tokens_spin.setValue(int(selected["max_output_tokens"]))
        dynamic_count = int(payload.get("dynamic_count") or 0)
        if payload.get("ok"):
            self.status_label.setText(
                f"Discovered {dynamic_count} live models; {len(suggestions)} total IDs remain selectable."
            )
        else:
            error = str(payload.get("error") or "Model discovery failed.")
            self.status_label.setText(
                f"Live discovery unavailable; {len(suggestions)} catalog/custom IDs remain selectable. {error}"
            )

    def _refresh_models_for_provider(self, provider_key: str, current_model: str) -> None:
        provider = self._provider_by_key.get(provider_key) or {}
        suggestions = [
            str(item)
            for item in provider.get("model_suggestions", [])
            if str(item).strip()
        ]
        default_model = str(provider.get("default_model") or "").strip()
        if default_model and default_model not in suggestions:
            suggestions.insert(0, default_model)
        requested_model = str(current_model or "").strip()
        if requested_model and requested_model not in suggestions:
            suggestions.insert(0, requested_model)
        model_text = requested_model or str(default_model or (suggestions[0] if suggestions else "")).strip()
        with QtCore.QSignalBlocker(self.model_combo):
            self.model_combo.clear()
            self.model_combo.addItems(suggestions)
            self.model_combo.setCurrentText(model_text)

    def _refresh_reasoning_for_provider(self, provider_key: str, current_effort: str) -> None:
        provider = self._provider_by_key.get(provider_key) or {}
        suggestions = [
            str(item)
            for item in provider.get("reasoning_efforts", [])
            if str(item).strip()
        ]
        default_effort = str(provider.get("default_reasoning_effort") or "default").strip() or "default"
        if default_effort and default_effort not in suggestions:
            suggestions.insert(0, default_effort)
        requested_effort = str(current_effort or "").strip()
        if requested_effort and requested_effort not in suggestions:
            suggestions.insert(0, requested_effort)
        effort_text = requested_effort or str(default_effort or (suggestions[0] if suggestions else "default")).strip()
        with QtCore.QSignalBlocker(self.reasoning_combo):
            self.reasoning_combo.clear()
            self.reasoning_combo.addItems(suggestions)
            self.reasoning_combo.setCurrentText(effort_text)

    def _refresh_api_styles_for_provider(self, provider_key: str, current_style: str) -> None:
        provider = self._provider_by_key.get(provider_key) or {}
        suggestions = ["provider-default"]
        for item in (*tuple(provider.get("api_styles", []) or []), *LLM_API_STYLE_OPTIONS):
            text = str(item or "").strip()
            if text and text not in suggestions:
                suggestions.append(text)
        requested = str(current_style or "provider-default").strip() or "provider-default"
        if requested not in suggestions:
            suggestions.insert(0, requested)
        with QtCore.QSignalBlocker(self.api_style_combo):
            self.api_style_combo.clear()
            self.api_style_combo.addItems(suggestions)
            self.api_style_combo.setCurrentText(requested)

    def _refresh_speed_for_provider(self, provider_key: str, current_speed: str) -> None:
        provider = self._provider_by_key.get(provider_key) or {}
        suggestions: list[str] = []
        for item in (*tuple(provider.get("speed_options", []) or []), *LLM_SPEED_OPTIONS):
            text = str(item or "").strip()
            if text and text not in suggestions:
                suggestions.append(text)
        requested = str(current_speed or provider.get("default_speed") or "default").strip() or "default"
        if requested not in suggestions:
            suggestions.insert(0, requested)
        with QtCore.QSignalBlocker(self.speed_combo):
            self.speed_combo.clear()
            self.speed_combo.addItems(suggestions)
            self.speed_combo.setCurrentText(requested)

    def _request_options_from_editor(self, *, show_error: bool) -> dict[str, object] | None:
        raw = str(self.request_options_edit.toPlainText() or "").strip()
        if not raw:
            return {}
        try:
            value = json.loads(raw)
        except (TypeError, ValueError) as exc:
            if show_error:
                QtWidgets.QMessageBox.warning(self, "Invalid advanced request JSON", str(exc))
            return None
        if not isinstance(value, dict):
            if show_error:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid advanced request JSON",
                    "Advanced request options must be a JSON object.",
                )
            return None
        return value

    def _current_config_from_widgets(self) -> dict[str, object]:
        config = dict(self._config)
        api_key = str(self.api_key_edit.text() or "").strip()
        config.update(
            {
                "llm_enabled": bool(self.enabled_check.isChecked()),
                "llm_provider": str(self.provider_combo.currentData() or "openai"),
                "llm_model": str(self.model_combo.currentText() or "").strip(),
                "llm_base_url": str(self.base_url_edit.text() or "").strip(),
                "llm_api_key_env": str(self.api_key_env_edit.text() or "").strip(),
                "llm_use_for": str(self.use_for_combo.currentData() or "advisory"),
                "llm_allow_public_network": bool(self.allow_public_network_check.isChecked()),
                "llm_api_style": str(self.api_style_combo.currentText() or "provider-default").strip(),
                "llm_reasoning_effort": str(self.reasoning_combo.currentText() or "default").strip(),
                "llm_speed": str(self.speed_combo.currentText() or "default").strip(),
                "llm_context_window": int(self.context_window_spin.value()),
                "llm_max_output_tokens": int(self.max_output_tokens_spin.value()),
                "llm_verbosity": str(self.verbosity_combo.currentText() or "default").strip(),
                "llm_temperature": None if self.temperature_spin.value() < 0 else float(self.temperature_spin.value()),
                "llm_top_p": None if self.top_p_spin.value() < 0 else float(self.top_p_spin.value()),
                "llm_timeout_seconds": int(self.timeout_spin.value()),
                "llm_request_options": self._request_options_from_editor(show_error=False) or {},
            }
        )
        if api_key and api_key != "********":
            config["llm_api_key"] = api_key
        return config

    def _current_payload_from_widgets(self) -> dict[str, object]:
        return build_llm_config_payload(self._current_config_from_widgets())

    def _set_status(self, payload: dict[str, object]) -> None:
        if not payload.get("enabled"):
            self.status_label.setText("LLM assistance disabled - enable it to edit provider and model settings.")
            return
        provider_label = str(payload.get("provider_label") or payload.get("provider") or "LLM")
        mode = str(payload.get("mode") or "")
        if payload.get("api_key_present"):
            credential_status = "token ready"
        elif mode == "local":
            credential_status = "token optional"
        else:
            credential_status = "token missing"
        reasoning = str(payload.get("reasoning_effort") or "default")
        api_style = str(payload.get("protocol") or payload.get("api_style") or "provider-default")
        speed = str(payload.get("speed") or "default")
        context_window = int(payload.get("context_window") or 0)
        context_label = f"{context_window:,}" if context_window else "model default"
        self.status_label.setText(
            f"{provider_label} ({mode}) - {credential_status} - {api_style} - "
            f"reasoning: {reasoning} - speed: {speed} - context: {context_label}"
        )


def create_llm_settings_panel(
    owner,
    parent: QtWidgets.QWidget | None = None,
    *,
    title: str = "AI / LLM Settings",
) -> LLMSettingsPanel:
    def _on_apply(panel: LLMSettingsPanel) -> None:
        for existing in list(getattr(owner, "_llm_settings_panels", []) or []):
            if existing is panel:
                continue
            try:
                existing.refresh_from_config()
            except Exception:
                pass
        try:
            owner._sync_service_config_snapshot()
        except Exception:
            pass
        try:
            owner.log("LLM settings updated.")
        except Exception:
            pass

    panel = LLMSettingsPanel(
        getattr(owner, "config", {}),
        title=title,
        parent=parent,
        on_apply=_on_apply,
    )
    panels = list(getattr(owner, "_llm_settings_panels", []) or [])
    panels.append(panel)
    owner._llm_settings_panels = panels
    return panel
