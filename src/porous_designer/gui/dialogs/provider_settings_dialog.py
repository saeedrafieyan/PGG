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
from porous_designer.agentic.credentials import delete_api_key, lookup_api_key, store_api_key
from porous_designer.agentic.provider import GeminiProvider, OpenAIProvider
from porous_designer.agentic.provider_config import (
    GEMINI_LOW_COST_MODEL,
    OPENAI_ESCALATION_MODEL,
    OPENAI_LOW_COST_MODEL,
    ProviderSettings,
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
        self.api_key.setPlaceholderText("Enter a new key to store via OS credential manager")
        self.key_source = QLabel("Key unavailable")
        form.addRow("External agent access", self.external_access)
        form.addRow("Provider", self.provider)
        form.addRow("Model", self.model)
        form.addRow("Model category", self.model_category)
        form.addRow("Timeout", self.timeout)
        form.addRow("Maximum retry count", self.retries)
        form.addRow("Reasoning level", self.reasoning)
        form.addRow("Confidence threshold", self.confidence_threshold)
        form.addRow("Escalation model", self.escalation_model)
        form.addRow("Escalation", self.require_escalation)
        form.addRow("Cache", self.cache_enabled)
        form.addRow("API-key source", self.key_source)
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
        self.store_key_button = QPushButton("Store Key")
        self.delete_key_button = QPushButton("Delete Stored Key")
        self.env_button = QPushButton("Use Environment Variable")
        self.clear_cache_button = QPushButton("Clear Provider Cache")
        self.close_button = QPushButton("Close")
        for button in (self.test_button, self.store_key_button, self.delete_key_button, self.env_button, self.clear_cache_button):
            buttons.addWidget(button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)
        layout.addLayout(buttons)
        self.provider.currentTextChanged.connect(self._provider_changed)
        self.external_access.toggled.connect(self._apply_to_settings)
        self.model.currentTextChanged.connect(self._apply_to_settings)
        self.timeout.valueChanged.connect(self._apply_to_settings)
        self.retries.valueChanged.connect(self._apply_to_settings)
        self.reasoning.currentTextChanged.connect(self._apply_to_settings)
        self.confidence_threshold.valueChanged.connect(self._apply_to_settings)
        self.escalation_model.currentTextChanged.connect(self._apply_to_settings)
        self.require_escalation.toggled.connect(self._apply_to_settings)
        self.cache_enabled.toggled.connect(self._apply_to_settings)
        self.store_key_button.clicked.connect(self._store_key)
        self.delete_key_button.clicked.connect(self._delete_key)
        self.env_button.clicked.connect(self._update_status)
        self.clear_cache_button.clicked.connect(lambda: ProviderResultCache().clear())
        self.test_button.clicked.connect(self._test_connection)
        self.close_button.clicked.connect(self.accept)

    def _sync_from_settings(self) -> None:
        self.external_access.setChecked(self.settings.external_access_enabled)
        self.provider.setCurrentText({"deterministic": "Deterministic only", "openai": "OpenAI", "gemini": "Gemini"}[self.settings.provider_mode.value])
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
        self._apply_to_settings()

    def _apply_to_settings(self) -> None:
        text = self.provider.currentText()
        self.settings.external_access_enabled = self.external_access.isChecked()
        self.settings.provider_mode = {"OpenAI": ProviderMode.OPENAI, "Gemini": ProviderMode.GEMINI}.get(text, ProviderMode.DETERMINISTIC_ONLY)
        if self.settings.provider_mode == ProviderMode.OPENAI:
            self.settings.openai_model = self.model.currentText()
        elif self.settings.provider_mode == ProviderMode.GEMINI:
            self.settings.gemini_model = self.model.currentText()
        self.settings.timeout_s = self.timeout.value()
        self.settings.max_retries = self.retries.value()
        self.settings.reasoning_level = self.reasoning.currentText()
        self.settings.confidence_threshold = self.confidence_threshold.value()
        self.settings.openai_escalation_model = self.escalation_model.currentText()
        self.settings.require_escalation_confirmation = self.require_escalation.isChecked()
        self.settings.cache_enabled = self.cache_enabled.isChecked()
        self.model_category.setText(self.settings.selected_category())
        self.settings_changed.emit(self.settings)
        self._update_status()

    def _update_status(self) -> None:
        if self.settings.provider_mode == ProviderMode.DETERMINISTIC_ONLY:
            self.key_source.setText("Deterministic-only mode")
            return
        result = lookup_api_key(self.settings.provider_mode.value)
        self.key_source.setText(f"{result.source}: {result.redacted_display}" if result.available else "Key unavailable")

    def _store_key(self) -> None:
        if self.settings.provider_mode == ProviderMode.DETERMINISTIC_ONLY:
            return
        key = self.api_key.text()
        if key:
            store_api_key(self.settings.provider_mode.value, key)
            self.api_key.clear()
            self._update_status()

    def _delete_key(self) -> None:
        if self.settings.provider_mode != ProviderMode.DETERMINISTIC_ONLY:
            delete_api_key(self.settings.provider_mode.value)
        self._update_status()

    def _test_connection(self) -> None:
        provider = None
        if self.settings.provider_mode == ProviderMode.OPENAI:
            provider = OpenAIProvider(self.settings)
        elif self.settings.provider_mode == ProviderMode.GEMINI:
            provider = GeminiProvider(self.settings)
        if provider is None:
            self.payload_preview.setPlainText("Deterministic-only mode: no connection test required.")
            return
        result = provider.test_connection()
        self.payload_preview.setPlainText(str(result))
