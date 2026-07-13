"""Provider-neutral agent interface for optional request interpretation."""

from __future__ import annotations

import concurrent.futures
import json
import time
from typing import Any, Protocol

from pydantic import ValidationError

from porous_designer.agentic.contracts import ParsedRequestResult, ProviderMetadata
from porous_designer.agentic.contracts import ProviderMode
from porous_designer.agentic.credentials import lookup_api_key
from porous_designer.agentic.provider_config import (
    GEMINI_LOW_COST_MODEL,
    OPENAI_LOW_COST_MODEL,
    ProviderSettings,
)
from porous_designer.agentic.provider_errors import classify_provider_exception


CONNECTION_PROBE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "ok": {"type": "boolean"},
        "provider": {"type": "string"},
    },
    "required": ["ok", "provider"],
}


class AgentProvider(Protocol):
    name: str
    enabled: bool

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        ...

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        ...

    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict:
        ...


class NoLLMProvider:
    name = "NoLLMProvider"
    enabled = True

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        return deterministic_evidence

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        return {"mode": "deterministic", "ambiguities": ambiguity_rules}

    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict:
        status = deterministic_result.get("status", "unknown")
        return {"summary": f"Deterministic feasibility status: {status}.", "status": status}


class MockAgentProvider:
    name = "MockAgentProvider"
    enabled = True

    def __init__(self, response: dict | None = None, *, invalid_json: bool = False, timeout: bool = False, metadata: dict | None = None) -> None:
        self.response = response
        self.invalid_json = invalid_json
        self.timeout = timeout
        self.metadata = metadata or {}

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        if self.timeout:
            raise TimeoutError("Mock provider timed out.")
        if self.invalid_json:
            return {"unexpected": "field"}
        result = self.response or deterministic_evidence
        if isinstance(result, dict):
            result = {**result, "provider_metadata": self.metadata}
        return result

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        return {"mode": "mock", "ambiguities": ambiguity_rules}

    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict:
        return {"summary": "Mock explanation follows deterministic status.", "status": deterministic_result.get("status")}


class ExternalAgentProviderAdapter:
    """Disabled-by-default adapter boundary for future external providers."""

    def __init__(self, *, enabled: bool = False, timeout_s: float = 10.0, provider_name: str = "external_json_provider") -> None:
        self.enabled = enabled
        self.timeout_s = timeout_s
        self.name = provider_name

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        if not self.enabled:
            raise RuntimeError("External agent access is disabled by default.")
        raise NotImplementedError("External provider transport is intentionally not configured in Phase 3B.1.")

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        if not self.enabled:
            raise RuntimeError("External agent access is disabled by default.")
        return {}


class StructuredProviderBase:
    sdk_module: str = ""
    env_provider_name: str = ""
    default_model: str = ""
    name: str = "provider"

    def __init__(self, settings: ProviderSettings | None = None, *, client: Any | None = None) -> None:
        self.settings = settings or ProviderSettings()
        self.model = self.settings.selected_model()
        self.timeout_s = self.settings.timeout_s
        self.enabled = self.settings.external_access_enabled
        self.client = client
        self.last_metadata: ProviderMetadata | None = None

    def parse_request(self, request: str, deterministic_evidence: dict, schema: dict) -> dict:
        self._ensure_configured()
        t0 = time.perf_counter()
        try:
            raw = self._call_structured(request, deterministic_evidence, schema)
            data = self._coerce_json(raw)
            result = ParsedRequestResult.model_validate(data)
            self.last_metadata = self._metadata(time.perf_counter() - t0, data, completion_status="success")
            result.provider_metadata = self.last_metadata.model_dump(mode="json")
            return result.model_dump(mode="json")
        except ValidationError as exc:
            raise ValueError(f"provider schema validation failed: {exc}") from exc
        except Exception:
            raise

    def explain_ambiguities(self, request: str, parsed_result: dict, ambiguity_rules: list[dict]) -> dict:
        return {"provider": self.name, "model": self.model, "ambiguities": ambiguity_rules}

    def explain_feasibility(self, deterministic_result: dict, approved_specification: dict) -> dict:
        status = deterministic_result.get("status", "unknown")
        return {
            "deterministic_status": status,
            "summary": f"Deterministic feasibility status remains {status}.",
            "reasons": [],
            "warnings": [],
            "suggested_user_actions": [],
        }

    def test_connection(self) -> dict:
        t0 = time.perf_counter()
        try:
            self._ensure_configured()
            raw = self._call_connection_probe()
            data = self._coerce_json(raw)
            if data.get("ok") is not True:
                raise ValueError(f"Provider probe returned unexpected payload: {data}")
            latency_s = time.perf_counter() - t0
            metadata = self._metadata(latency_s, data, completion_status="connection_probe_success")
            self.last_metadata = metadata
            return {
                "ok": True,
                "provider": self.name,
                "model": self.model,
                "structured_output": True,
                "latency_s": latency_s,
                "metadata": metadata.model_dump(mode="json"),
            }
        except Exception as exc:
            error = classify_provider_exception(self.name, self.model, exc)
            return {"ok": False, "provider": self.name, "model": self.model, "error": error.model_dump(mode="json")}

    def _ensure_configured(self) -> None:
        if not self.enabled:
            raise RuntimeError("External agent access is disabled by default.")
        credential = lookup_api_key(self.env_provider_name, self.settings.credential_mode)
        if not credential.available and self.client is None:
            raise RuntimeError(f"{self.name} API key is unavailable.")

    def _call_structured(self, request: str, deterministic_evidence: dict, schema: dict) -> Any:
        if self.client is not None:
            return self._call_client(request, deterministic_evidence, schema)
        self.client = self._create_client()
        return self._call_client(request, deterministic_evidence, schema)

    def _create_client(self) -> Any:
        raise NotImplementedError(f"{self.name} SDK is optional and no client was supplied.")

    def _call_client(self, request: str, deterministic_evidence: dict, schema: dict) -> Any:
        raise NotImplementedError

    def _call_connection_probe(self) -> Any:
        raise NotImplementedError

    def _coerce_json(self, raw: Any) -> dict:
        if isinstance(raw, ParsedRequestResult):
            return raw.model_dump(mode="json")
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            return json.loads(raw)
        text = getattr(raw, "output_text", None) or getattr(raw, "text", None)
        if text:
            return json.loads(text)
        raise ValueError("Provider returned unsupported response type.")

    def _metadata(self, latency_s: float, data: dict, *, completion_status: str) -> ProviderMetadata:
        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        return ProviderMetadata(
            provider=self.name,
            model=self.model,
            model_category=self.settings.selected_category(),
            latency_s=latency_s,
            retries=0,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            total_tokens=usage.get("total_tokens"),
            cached_tokens=usage.get("cached_tokens"),
            completion_status=completion_status,
        )


class OpenAIProvider(StructuredProviderBase):
    name = "openai"
    env_provider_name = "openai"
    default_model = OPENAI_LOW_COST_MODEL

    def __init__(self, settings: ProviderSettings | None = None, *, client: Any | None = None) -> None:
        settings = settings or ProviderSettings(provider_mode=ProviderMode.OPENAI)
        if settings.provider_mode != ProviderMode.OPENAI:
            settings.provider_mode = ProviderMode.OPENAI
        super().__init__(settings, client=client)
        self.model = settings.openai_model if not settings.custom_model_id else settings.custom_model_id

    def _call_client(self, request: str, deterministic_evidence: dict, schema: dict) -> Any:
        payload = [
            {"role": "system", "content": "Return only JSON matching ParsedRequestResult. Do not use tools, files, web search, code, or hidden reasoning."},
            {"role": "user", "content": json.dumps({"request": request, "deterministic_evidence": deterministic_evidence, "schema": schema}, default=str)},
        ]
        if hasattr(self.client, "responses"):
            response = self.client.responses.create(
                model=self.model,
                input=payload,
                text={"format": {"type": "json_schema", "name": "ParsedRequestResult", "schema": schema, "strict": True}},
                max_output_tokens=1400,
                timeout=self.timeout_s,
            )
            return getattr(response, "output_text", response)
        return self.client.create(model=self.model, messages=payload, response_format={"type": "json_schema", "json_schema": {"name": "ParsedRequestResult", "schema": schema, "strict": True}})

    def _call_connection_probe(self) -> Any:
        if self.client is None:
            self.client = self._create_client()
        prompt = "Return JSON with ok=true and provider='openai'."
        if hasattr(self.client, "responses"):
            response = self.client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": "Return only JSON matching the supplied schema."},
                    {"role": "user", "content": prompt},
                ],
                text={"format": {"type": "json_schema", "name": "ConnectionProbe", "schema": CONNECTION_PROBE_SCHEMA, "strict": True}},
                max_output_tokens=80,
                timeout=self.timeout_s,
            )
            return getattr(response, "output_text", response)
        return self.client.create(
            model=self.model,
            messages=[
                {"role": "system", "content": "Return only JSON matching the supplied schema."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_schema", "json_schema": {"name": "ConnectionProbe", "schema": CONNECTION_PROBE_SCHEMA, "strict": True}},
        )

    def _create_client(self) -> Any:
        credential = lookup_api_key(self.env_provider_name, self.settings.credential_mode)
        if not credential.available or not credential.key:
            raise RuntimeError("OpenAI API key is unavailable.")
        try:
            from openai import OpenAI
        except Exception as exc:
            raise RuntimeError("OpenAI SDK is not installed or could not be loaded.") from exc
        return OpenAI(api_key=credential.key, timeout=self.timeout_s)


class GeminiProvider(StructuredProviderBase):
    name = "gemini"
    env_provider_name = "gemini"
    default_model = GEMINI_LOW_COST_MODEL

    def __init__(self, settings: ProviderSettings | None = None, *, client: Any | None = None) -> None:
        settings = settings or ProviderSettings(provider_mode=ProviderMode.GEMINI)
        if settings.provider_mode != ProviderMode.GEMINI:
            settings.provider_mode = ProviderMode.GEMINI
        super().__init__(settings, client=client)
        self.model = settings.gemini_model if not settings.custom_model_id else settings.custom_model_id

    def _call_client(self, request: str, deterministic_evidence: dict, schema: dict) -> Any:
        prompt = json.dumps(
            {
                "instruction": "Return only JSON matching ParsedRequestResult. Do not use tools, search, code, files, or hidden reasoning.",
                "request": request,
                "deterministic_evidence": deterministic_evidence,
                "schema": schema,
            },
            default=str,
        )
        if hasattr(self.client, "interactions"):
            response = self.client.interactions.create(
                model=self.model,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": schema,
                },
            )
            return getattr(response, "output_text", response)
        if hasattr(self.client, "models"):
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"response_mime_type": "application/json", "response_schema": schema, "max_output_tokens": 1400},
            )
            return getattr(response, "text", response)
        return self.client.generate_content(model=self.model, contents=prompt, generation_config={"response_mime_type": "application/json", "response_schema": schema})

    def _call_connection_probe(self) -> Any:
        if self.client is None:
            self.client = self._create_client()
        prompt = "Return JSON with ok=true and provider='gemini'."
        if hasattr(self.client, "interactions"):
            response = self.client.interactions.create(
                model=self.model,
                input=prompt,
                response_format={
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": CONNECTION_PROBE_SCHEMA,
                },
            )
            return getattr(response, "output_text", response)
        if hasattr(self.client, "models"):
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={"response_mime_type": "application/json", "response_schema": CONNECTION_PROBE_SCHEMA, "max_output_tokens": 80},
            )
            return getattr(response, "text", response)
        return self.client.generate_content(model=self.model, contents=prompt, generation_config={"response_mime_type": "application/json", "response_schema": CONNECTION_PROBE_SCHEMA})

    def _create_client(self) -> Any:
        credential = lookup_api_key(self.env_provider_name, self.settings.credential_mode)
        if not credential.available or not credential.key:
            raise RuntimeError("Gemini API key is unavailable.")
        try:
            from google import genai
        except Exception as exc:
            raise RuntimeError("Google GenAI SDK is not installed or could not be loaded.") from exc
        return genai.Client(api_key=credential.key)


def call_provider_with_timeout(provider: AgentProvider, request: str, deterministic_evidence: dict, schema: dict, *, timeout_s: float = 10.0) -> ParsedRequestResult:
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(provider.parse_request, request, deterministic_evidence, schema)
        raw = future.result(timeout=timeout_s)
    if isinstance(raw, str):
        raw = json.loads(raw)
    return ParsedRequestResult.model_validate(raw)
