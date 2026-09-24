"""Agent provider settings dialog (OpenRouter)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from porous_designer.agentic.cache import ProviderResultCache
from porous_designer.agentic.contracts import ProviderMode
from porous_designer.agentic.credentials import clear_session_key, delete_api_key, lookup_api_key, store_api_key, store_session_key
from porous_designer.agentic.openrouter import ModelCatalog, OpenRouterClient
from porous_designer.agentic.provider import OpenRouterProvider
from porous_designer.agentic.provider_config import (
    OPENROUTER_DEFAULT_FALLBACK_MODELS,
    OPENROUTER_DEFAULT_MODEL,
    CredentialMode,
    ExternalCallMode,
    ProviderSettings,
    save_provider_settings,
)

PROVIDER_LABELS = {ProviderMode.DETERMINISTIC_ONLY: "Deterministic only", ProviderMode.OPENROUTER: "OpenRouter"}
CREDENTIAL_KEY = "openrouter"


def _catalog() -> ModelCatalog:
    from porous_designer.paths import cache_dir

    return ModelCatalog(OpenRouterClient(None, timeout_s=20.0), cache_path=cache_dir() / "openrouter_models.json")


class ProviderSettingsDialog(QDialog):
    settings_changed = Signal(object)

    def __init__(self, settings: ProviderSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Agent Provider Settings")
        self.resize(720, 680)
        self._build_ui()
        self._sync_from_settings()
        self._update_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.external_access = QCheckBox("Enable external agent access")
        self.provider = QComboBox()
        self.provider.addItems(list(PROVIDER_LABELS.values()))
        self.call_mode = QComboBox()
        self.call_mode.addItems(["Deterministic only", "External when recommended", "Always use external interpretation"])
        self.credential_mode = QComboBox()
        self.credential_mode.addItems(["Environment variable", "Credential store", "Session only"])
        self.model = QComboBox()
        self.model.setEditable(True)
        self.fallback_models = QLineEdit()
        self.fallback_models.setPlaceholderText("Comma-separated OpenRouter model ids tried in order if the main model is unavailable")
        self.model_category = QLabel("None")
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(5.0, 300.0)
        self.timeout.setSuffix(" s")
        self.total_deadline = QDoubleSpinBox()
        self.total_deadline.setRange(10.0, 900.0)
        self.total_deadline.setSuffix(" s")
        self.retries = QSpinBox()
        self.retries.setRange(0, 4)
        self.temperature = QDoubleSpinBox()
        self.temperature.setRange(0.0, 1.0)
        self.temperature.setSingleStep(0.1)
        self.temperature.setDecimals(2)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_000_000_000)
        self.max_tokens = QSpinBox()
        self.max_tokens.setRange(500, 16000)
        self.max_tokens.setSingleStep(500)
        self.reasoning = QComboBox()
        self.reasoning.addItems(["low", "medium", "high"])
        self.allow_data_collection = QCheckBox("Allow endpoints that may store or train on prompts (needed by some free models)")
        self.cache_enabled = QCheckBox("Enable validated-result cache")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("Enter a new OpenRouter key for the selected credential mode")
        self.key_source = QLabel("Key unavailable")
        self.key_source.setWordWrap(True)
        form.addRow("External agent access", self.external_access)
        form.addRow("Provider", self.provider)
        form.addRow("External-call mode", self.call_mode)
        form.addRow("Model", self.model)
        form.addRow("Fallback models", self.fallback_models)
        form.addRow("Model category", self.model_category)
        form.addRow("Request timeout", self.timeout)
        form.addRow("Total time budget", self.total_deadline)
        form.addRow("Maximum retry count", self.retries)
        form.addRow("Temperature (0 = faithful)", self.temperature)
        form.addRow("Seed", self.seed)
        form.addRow("Max output tokens", self.max_tokens)
        form.addRow("Reasoning effort", self.reasoning)
        form.addRow("Data policy", self.allow_data_collection)
        form.addRow("Cache", self.cache_enabled)
        form.addRow("Credential mode", self.credential_mode)
        form.addRow("Credential status", self.key_source)
        form.addRow("Store new key", self.api_key)
        layout.addLayout(form)
        self.privacy = QLabel(
            "No external LLM is required to use AGE. Only the request text is sent; every value the model proposes must quote your request "
            "and is checked before it is shown. API keys are never stored in normal settings, logs, audit files, or request payloads."
        )
        self.privacy.setWordWrap(True)
        layout.addWidget(self.privacy)
        self.payload_preview = QTextEdit()
        self.payload_preview.setReadOnly(True)
        self.payload_preview.setPlaceholderText("Connection and save results appear here.")
        layout.addWidget(self.payload_preview)
        buttons = QHBoxLayout()
        self.test_button = QPushButton("Test Connection")
        self.refresh_models_button = QPushButton("Refresh Free Models")
        self.apply_button = QPushButton("Apply")
        self.save_button = QPushButton("Save")
        self.delete_key_button = QPushButton("Delete Stored Key")
        self.env_button = QPushButton("Use Environment Variable")
        self.clear_cache_button = QPushButton("Clear Provider Cache")
        self.cancel_button = QPushButton("Cancel")
        for button in (self.test_button, self.refresh_models_button, self.apply_button, self.save_button, self.delete_key_button, self.env_button, self.clear_cache_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.provider.currentTextChanged.connect(self._provider_changed)
        self.external_access.toggled.connect(self._external_access_toggled)
        self.call_mode.currentTextChanged.connect(self._update_model_category)
        self.model.currentTextChanged.connect(self._update_model_category)
        self.credential_mode.currentTextChanged.connect(self._update_status)
        self.apply_button.clicked.connect(lambda: self._save_or_apply(close=False))
        self.save_button.clicked.connect(lambda: self._save_or_apply(close=True))
        self.delete_key_button.clicked.connect(self._delete_key)
        self.env_button.clicked.connect(lambda: self.credential_mode.setCurrentText("Environment variable"))
        self.clear_cache_button.clicked.connect(lambda: ProviderResultCache().clear())
        self.test_button.clicked.connect(self._test_connection)
        self.refresh_models_button.clicked.connect(self._refresh_models)
        self.cancel_button.clicked.connect(self._cancel)

    def _external_access_toggled(self, checked: bool) -> None:
        if checked and self.provider.currentText() != "Deterministic only" and self.call_mode.currentText() == "Deterministic only":
            self.call_mode.setCurrentText("External when recommended")
        self._update_status()

    def _sync_from_settings(self) -> None:
        s = self.settings
        self.external_access.setChecked(s.external_access_enabled)
        self.provider.setCurrentText(PROVIDER_LABELS[s.provider_mode])
        self.call_mode.setCurrentText(
            {
                "deterministic_only": "Deterministic only",
                "external_when_recommended": "External when recommended",
                "always_external": "Always use external interpretation",
            }[s.external_call_mode.value]
        )
        self.credential_mode.setCurrentText({"environment": "Environment variable", "keyring": "Credential store", "session": "Session only"}[s.credential_mode.value])
        self.timeout.setValue(s.timeout_s)
        self.total_deadline.setValue(s.total_deadline_s)
        self.retries.setValue(s.max_retries)
        self.temperature.setValue(s.temperature)
        self.seed.setValue(s.seed)
        self.max_tokens.setValue(s.max_output_tokens)
        self.reasoning.setCurrentText(s.reasoning_level)
        self.allow_data_collection.setChecked(s.allow_provider_data_collection)
        self.cache_enabled.setChecked(s.cache_enabled)
        self.fallback_models.setText(", ".join(s.openrouter_fallback_models))
        self._provider_changed()

    def _model_items(self) -> list[str]:
        items = [OPENROUTER_DEFAULT_MODEL, *OPENROUTER_DEFAULT_FALLBACK_MODELS]
        try:
            # Cached catalog only; the network is used by "Refresh Free Models".
            catalog = _catalog()
            cached = catalog.cached_entries()
            for model_id, entry in sorted(cached.items()):
                params = set(entry.get("supported_parameters") or [])
                if model_id.endswith(":free") and "structured_outputs" in params and model_id not in items:
                    items.append(model_id)
        except Exception:
            pass
        return items

    def _provider_changed(self) -> None:
        current = self.provider.currentText()
        self.model.blockSignals(True)
        self.model.clear()
        if current == "OpenRouter":
            self.model.addItems(self._model_items())
            self.model.setCurrentText(self.settings.openrouter_model)
            self.fallback_models.setEnabled(True)
        else:
            self.model.addItems(["deterministic"])
            self.fallback_models.setEnabled(False)
        self.model.blockSignals(False)
        self._update_model_category()

    def _read_controls(self) -> ProviderSettings:
        settings = self.settings.copy()
        settings.external_access_enabled = self.external_access.isChecked()
        settings.provider_mode = ProviderMode.OPENROUTER if self.provider.currentText() == "OpenRouter" else ProviderMode.DETERMINISTIC_ONLY
        settings.external_call_mode = {
            "External when recommended": ExternalCallMode.WHEN_RECOMMENDED,
            "Always use external interpretation": ExternalCallMode.ALWAYS,
        }.get(self.call_mode.currentText(), ExternalCallMode.DETERMINISTIC_ONLY)
        settings.credential_mode = {
            "Environment variable": CredentialMode.ENVIRONMENT,
            "Session only": CredentialMode.SESSION,
        }.get(self.credential_mode.currentText(), CredentialMode.KEYRING)
        if settings.provider_mode == ProviderMode.OPENROUTER:
            settings.openrouter_model = self.model.currentText().strip() or OPENROUTER_DEFAULT_MODEL
            settings.openrouter_fallback_models = [m.strip() for m in self.fallback_models.text().split(",") if m.strip()]
        settings.timeout_s = self.timeout.value()
        settings.total_deadline_s = max(self.total_deadline.value(), self.timeout.value())
        settings.max_retries = self.retries.value()
        settings.temperature = self.temperature.value()
        settings.seed = self.seed.value()
        settings.max_output_tokens = self.max_tokens.value()
        settings.reasoning_level = self.reasoning.currentText()
        settings.allow_provider_data_collection = self.allow_data_collection.isChecked()
        settings.cache_enabled = self.cache_enabled.isChecked()
        return settings

    def _update_model_category(self) -> None:
        settings = self._read_controls()
        self.model_category.setText(settings.selected_category())
        self._update_status()

    def _update_status(self) -> None:
        settings = self._read_controls()
        if settings.provider_mode == ProviderMode.DETERMINISTIC_ONLY:
            self.key_source.setText("Deterministic-only mode")
            return
        result = lookup_api_key(CREDENTIAL_KEY, settings.credential_mode)
        source = {"environment": "Environment variable OPENROUTER_API_KEY", "keyring": "Windows Credential Manager", "session": "Session only"}.get(result.source, result.source)
        status = "Available" if result.available else "Not found"
        fp = f", fingerprint: ...{result.redacted_display[-4:]}" if result.redacted_display and result.redacted_display != "[REDACTED]" else ""
        self.key_source.setText(f"Stored key: {status}; Key source: {source}{fp}; {result.message}")

    def _save_key_if_needed(self, settings: ProviderSettings) -> str:
        key = self.api_key.text().strip()
        if not key or settings.provider_mode == ProviderMode.DETERMINISTIC_ONLY:
            return "No new key entered"
        if settings.credential_mode == CredentialMode.SESSION:
            store_session_key(CREDENTIAL_KEY, key)
            message = "Session-only credential active"
        elif settings.credential_mode == CredentialMode.KEYRING:
            store_api_key(CREDENTIAL_KEY, key)
            message = "Stored credential verified"
        else:
            message = "Environment mode selected; key text was not stored"
        self.api_key.clear()
        return message

    def _save_or_apply(self, *, close: bool) -> None:
        settings = self._read_controls()
        try:
            credential_message = self._save_key_if_needed(settings)
            if settings.provider_mode != ProviderMode.DETERMINISTIC_ONLY and settings.credential_mode != CredentialMode.ENVIRONMENT:
                result = lookup_api_key(CREDENTIAL_KEY, settings.credential_mode)
                if not result.available:
                    raise RuntimeError(result.message or "Credential is unavailable after save.")
            settings.bump_version()
            save_provider_settings(settings)
            self.settings = settings
            self.settings_changed.emit(settings)
            self._update_status()
            self.payload_preview.setPlainText(f"Settings saved\n{credential_message}\nActive provider rebuilt")
            if close:
                self.accept()
        except Exception as exc:
            self.payload_preview.setPlainText(f"Settings not saved: {exc}")

    def _delete_key(self) -> None:
        settings = self._read_controls()
        try:
            if settings.provider_mode == ProviderMode.DETERMINISTIC_ONLY:
                self.payload_preview.setPlainText("Deterministic-only mode: no credential to delete.")
            elif settings.credential_mode == CredentialMode.SESSION:
                clear_session_key(CREDENTIAL_KEY)
                self.payload_preview.setPlainText("Session-only credential cleared.")
            elif settings.credential_mode == CredentialMode.ENVIRONMENT:
                self.payload_preview.setPlainText("Environment credentials are managed outside AGE.")
            else:
                delete_api_key(CREDENTIAL_KEY)
                self.payload_preview.setPlainText("Stored credential deleted.")
        except Exception as exc:
            self.payload_preview.setPlainText(f"Credential delete failed: {exc}")
        finally:
            self._update_status()

    def _refresh_models(self) -> None:
        try:
            catalog = _catalog()
            catalog.ttl_s = 0.0
            free = catalog.free_structured_models()
            if catalog.last_error:
                raise RuntimeError(catalog.last_error)
            current = self.model.currentText()
            self._provider_changed()
            self.model.setCurrentText(current)
            listing = "\n".join(f"  {c.model_id}" + ("  (seed)" if c.supports("seed") else "") for c in free)
            self.payload_preview.setPlainText(f"Free models with strict structured output ({len(free)}):\n{listing}")
        except Exception as exc:
            self.payload_preview.setPlainText(f"Model list refresh failed: {exc}")

    def _test_connection(self) -> None:
        settings = self._read_controls()
        entered_key = self.api_key.text().strip()
        original_credential_mode = settings.credential_mode
        if settings.provider_mode == ProviderMode.DETERMINISTIC_ONLY:
            self.payload_preview.setPlainText("Deterministic-only mode: no connection test required.")
            return
        if entered_key:
            store_session_key(CREDENTIAL_KEY, entered_key)
            settings.credential_mode = CredentialMode.SESSION
        settings.external_access_enabled = True
        try:
            provider = OpenRouterProvider(settings)
            result = provider.test_connection()
            source = "entered key, session test" if entered_key else settings.credential_mode.value
            lines = [
                f"Provider: {settings.provider_mode.value}",
                f"Model: {settings.selected_model()}",
                f"Key source: {source}",
                f"Connection result: {'successful' if result.get('ok') else 'failed'}",
            ]
            key = result.get("key") or {}
            daily = key.get("free_model_daily_requests")
            if daily:
                lines.append(f"Free-model requests today: {daily}")
            for model in result.get("models", []):
                lines.append(f"  {model['model']}: listed={model['listed']}, output={model['output_mode']}, seed={model['seed_supported']}")
            if result.get("error"):
                lines.append(f"Error: {result['error'].get('category')}: {result['error'].get('safe_user_message')}")
            lines += ["Settings saved: no", "Deterministic fallback remains available"]
            self.payload_preview.setPlainText("\n".join(lines))
        finally:
            if entered_key and original_credential_mode != CredentialMode.SESSION:
                clear_session_key(CREDENTIAL_KEY)

    def _cancel(self) -> None:
        self.api_key.clear()
        self.reject()
