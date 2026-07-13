"""Agent provider settings dialog."""

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
from porous_designer.agentic.provider import GeminiProvider, OpenAIProvider
from porous_designer.agentic.provider_config import (
    CredentialMode,
    ExternalCallMode,
    GEMINI_LOW_COST_MODEL,
    OPENAI_ESCALATION_MODEL,
    OPENAI_LOW_COST_MODEL,
    ProviderSettings,
    save_provider_settings,
)


class ProviderSettingsDialog(QDialog):
    settings_changed = Signal(object)

    def __init__(self, settings: ProviderSettings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Agent Provider Settings")
        self.resize(680, 620)
        self._build_ui()
        self._sync_from_settings()
        self._update_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.external_access = QCheckBox("Enable external agent access")
        self.provider = QComboBox()
        self.provider.addItems(["Deterministic only", "OpenAI", "Gemini"])
        self.call_mode = QComboBox()
        self.call_mode.addItems(["Deterministic only", "External when recommended", "Always use external interpretation"])
        self.credential_mode = QComboBox()
        self.credential_mode.addItems(["Environment variable", "Credential store", "Session only"])
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model_category = QLabel("None")
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1.0, 120.0)
        self.timeout.setSuffix(" s")
        self.retries = QSpinBox()
        self.retries.setRange(0, 3)
        self.reasoning = QComboBox()
        self.reasoning.addItems(["low", "medium"])
        self.confidence_threshold = QDoubleSpinBox()
        self.confidence_threshold.setRange(0.0, 1.0)
        self.confidence_threshold.setDecimals(2)
        self.escalation_model = QComboBox()
        self.escalation_model.setEditable(True)
        self.escalation_model.addItems([OPENAI_ESCALATION_MODEL])
        self.require_escalation = QCheckBox("Require confirmation before escalation")
        self.cache_enabled = QCheckBox("Enable validated-result cache")
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("Enter a new key for the selected credential mode")
        self.key_source = QLabel("Key unavailable")
        form.addRow("External agent access", self.external_access)
        form.addRow("Provider", self.provider)
        form.addRow("External-call mode", self.call_mode)
        form.addRow("Model", self.model)
        form.addRow("Model category", self.model_category)
        form.addRow("Timeout", self.timeout)
        form.addRow("Maximum retry count", self.retries)
        form.addRow("Reasoning level", self.reasoning)
        form.addRow("Confidence threshold", self.confidence_threshold)
        form.addRow("Escalation model", self.escalation_model)
        form.addRow("Escalation", self.require_escalation)
        form.addRow("Cache", self.cache_enabled)
        form.addRow("Credential mode", self.credential_mode)
        form.addRow("Credential status", self.key_source)
        form.addRow("Store new key", self.api_key)
        layout.addLayout(form)
        self.privacy = QLabel("No external LLM is required to use PGG. API keys are never stored in normal settings, logs, audit files, or request payloads.")
        self.privacy.setWordWrap(True)
        layout.addWidget(self.privacy)
        self.payload_preview = QTextEdit()
        self.payload_preview.setReadOnly(True)
        self.payload_preview.setPlaceholderText("Payload review appears before external requests.")
        layout.addWidget(self.payload_preview)
        buttons = QHBoxLayout()
        self.test_button = QPushButton("Test Connection")
        self.apply_button = QPushButton("Apply")
        self.save_button = QPushButton("Save")
        self.delete_key_button = QPushButton("Delete Stored Key")
        self.env_button = QPushButton("Use Environment Variable")
        self.clear_cache_button = QPushButton("Clear Provider Cache")
        self.cancel_button = QPushButton("Cancel")
        for button in (self.test_button, self.apply_button, self.save_button, self.delete_key_button, self.env_button, self.clear_cache_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(self.cancel_button)
        layout.addLayout(buttons)
        self.provider.currentTextChanged.connect(self._provider_changed)
        self.external_access.toggled.connect(self._external_access_toggled)
        self.call_mode.currentTextChanged.connect(self._update_model_category)
        self.credential_mode.currentTextChanged.connect(self._update_status)
        self.apply_button.clicked.connect(lambda: self._save_or_apply(close=False))
        self.save_button.clicked.connect(lambda: self._save_or_apply(close=True))
        self.delete_key_button.clicked.connect(self._delete_key)
        self.env_button.clicked.connect(lambda: self.credential_mode.setCurrentText("Environment variable"))
        self.clear_cache_button.clicked.connect(lambda: ProviderResultCache().clear())
        self.test_button.clicked.connect(self._test_connection)
        self.cancel_button.clicked.connect(self._cancel)

    def _external_access_toggled(self, checked: bool) -> None:
        if checked and self.provider.currentText() != "Deterministic only" and self.call_mode.currentText() == "Deterministic only":
            self.call_mode.setCurrentText("External when recommended")
        self._update_status()

    def _sync_from_settings(self) -> None:
        self.external_access.setChecked(self.settings.external_access_enabled)
        self.provider.setCurrentText({"deterministic": "Deterministic only", "openai": "OpenAI", "gemini": "Gemini"}[self.settings.provider_mode.value])
        self.call_mode.setCurrentText(
            {
                "deterministic_only": "Deterministic only",
                "external_when_recommended": "External when recommended",
                "always_external": "Always use external interpretation",
            }[self.settings.external_call_mode.value]
        )
        self.credential_mode.setCurrentText(
            {
                "environment": "Environment variable",
                "keyring": "Credential store",
                "session": "Session only",
            }[self.settings.credential_mode.value]
        )
        self.timeout.setValue(self.settings.timeout_s)
        self.retries.setValue(self.settings.max_retries)
        self.reasoning.setCurrentText(self.settings.reasoning_level)
        self.confidence_threshold.setValue(self.settings.confidence_threshold)
        self.escalation_model.setCurrentText(self.settings.openai_escalation_model)
        self.require_escalation.setChecked(self.settings.require_escalation_confirmation)
        self.cache_enabled.setChecked(self.settings.cache_enabled)
        self._provider_changed()

    def _provider_changed(self) -> None:
        current = self.provider.currentText()
        self.model.blockSignals(True)
        self.model.clear()
        if current == "OpenAI":
            self.model.addItems([OPENAI_LOW_COST_MODEL, OPENAI_ESCALATION_MODEL])
            self.model.setCurrentText(self.settings.openai_model)
        elif current == "Gemini":
            self.model.addItems([GEMINI_LOW_COST_MODEL])
            self.model.setCurrentText(self.settings.gemini_model)
        else:
            self.model.addItems(["deterministic"])
        self.model.blockSignals(False)
        self._update_model_category()

    def _read_controls(self) -> ProviderSettings:
        text = self.provider.currentText()
        settings = ProviderSettings(**self.settings.__dict__)
        settings.external_access_enabled = self.external_access.isChecked()
        settings.provider_mode = {"OpenAI": ProviderMode.OPENAI, "Gemini": ProviderMode.GEMINI}.get(text, ProviderMode.DETERMINISTIC_ONLY)
        settings.external_call_mode = {
            "External when recommended": ExternalCallMode.WHEN_RECOMMENDED,
            "Always use external interpretation": ExternalCallMode.ALWAYS,
        }.get(self.call_mode.currentText(), ExternalCallMode.DETERMINISTIC_ONLY)
        settings.credential_mode = {
            "Environment variable": CredentialMode.ENVIRONMENT,
            "Session only": CredentialMode.SESSION,
        }.get(self.credential_mode.currentText(), CredentialMode.KEYRING)
        if settings.provider_mode == ProviderMode.OPENAI:
            settings.openai_model = self.model.currentText()
        elif settings.provider_mode == ProviderMode.GEMINI:
            settings.gemini_model = self.model.currentText()
        settings.timeout_s = self.timeout.value()
        settings.max_retries = self.retries.value()
        settings.reasoning_level = self.reasoning.currentText()
        settings.confidence_threshold = self.confidence_threshold.value()
        settings.openai_escalation_model = self.escalation_model.currentText()
        settings.require_escalation_confirmation = self.require_escalation.isChecked()
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
        result = lookup_api_key(settings.provider_mode.value, settings.credential_mode)
        source = {
            "environment": "Environment variable",
            "keyring": "Windows Credential Manager",
            "session": "Session only",
        }.get(result.source, result.source)
        status = "Available" if result.available else "Not found"
        fp = f", fingerprint: ...{result.redacted_display[-4:]}" if result.redacted_display and result.redacted_display != "[REDACTED]" else ""
        self.key_source.setText(f"Stored key: {status}; Key source: {source}; Key identifier: {settings.provider_mode.value}{fp}; {result.message}")

    def _save_key_if_needed(self, settings: ProviderSettings) -> str:
        key = self.api_key.text()
        if not key or settings.provider_mode == ProviderMode.DETERMINISTIC_ONLY:
            return "No new key entered"
        if settings.credential_mode == CredentialMode.SESSION:
            store_session_key(settings.provider_mode.value, key)
            message = "Session-only credential active"
        elif settings.credential_mode == CredentialMode.KEYRING:
            store_api_key(settings.provider_mode.value, key)
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
                result = lookup_api_key(settings.provider_mode.value, settings.credential_mode)
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
                clear_session_key(settings.provider_mode.value)
                self.payload_preview.setPlainText("Session-only credential cleared.")
            elif settings.credential_mode == CredentialMode.ENVIRONMENT:
                self.payload_preview.setPlainText("Environment credentials are managed outside PGG.")
            else:
                delete_api_key(settings.provider_mode.value)
                self.payload_preview.setPlainText("Stored credential deleted.")
        except Exception as exc:
            self.payload_preview.setPlainText(f"Credential delete failed: {exc}")
        finally:
            self._update_status()

    def _test_connection(self) -> None:
        settings = self._read_controls()
        entered_key = self.api_key.text()
        original_credential_mode = settings.credential_mode
        if entered_key and settings.provider_mode != ProviderMode.DETERMINISTIC_ONLY:
            store_session_key(settings.provider_mode.value, entered_key)
            settings.credential_mode = CredentialMode.SESSION
        if settings.provider_mode != ProviderMode.DETERMINISTIC_ONLY:
            settings.external_access_enabled = True
        provider = None
        if settings.provider_mode == ProviderMode.OPENAI:
            provider = OpenAIProvider(settings)
        elif settings.provider_mode == ProviderMode.GEMINI:
            provider = GeminiProvider(settings)
        if provider is None:
            self.payload_preview.setPlainText("Deterministic-only mode: no connection test required.")
            return
        try:
            result = provider.test_connection()
            source = "entered key, session test" if entered_key else settings.credential_mode.value
            self.payload_preview.setPlainText(
                "\n".join(
                    [
                        f"Provider: {settings.provider_mode.value}",
                        f"Model: {settings.selected_model()}",
                        f"Key source: {source}",
                        f"Connection result: {'successful' if result.get('ok') else 'failed'}",
                        f"Result: {result}",
                        "Settings saved: no",
                        "Deterministic fallback remains available",
                    ]
                )
            )
        finally:
            if entered_key and original_credential_mode != CredentialMode.SESSION:
                clear_session_key(settings.provider_mode.value)

    def _cancel(self) -> None:
        self.api_key.clear()
        self.reject()
