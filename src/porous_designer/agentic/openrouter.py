"""Minimal OpenRouter HTTP client, model catalog, and error mapping.

OpenRouter exposes an OpenAI-compatible chat-completions API. This module uses
``httpx`` directly instead of an SDK so every request field that affects
faithfulness (``provider.require_parameters``, ``data_collection``, the
structured-output format, sampling parameters) is explicit and auditable.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from porous_designer.agentic.contracts import ProviderErrorCategory
from porous_designer.agentic.provider_errors import redact_secrets

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
APP_TITLE = "AGE - Agentic Geometry Engineering"
CATALOG_TTL_S = 6 * 3600.0
# A 429 whose reset is further away than this is a quota (e.g. the free-tier
# daily cap), not a transient burst; retrying the same model is pointless.
MAX_RATE_LIMIT_WAIT_S = 20.0

OutputMode = Literal["json_schema", "json_object", "prompt_only"]


class OpenRouterError(RuntimeError):
    """A failed OpenRouter call, classified for retry and fallback decisions."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None,
        category: ProviderErrorCategory,
        retryable: bool,
        try_next_model: bool,
        retry_after_s: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(redact_secrets(message))
        self.status = status
        self.category = category
        self.retryable = retryable
        self.try_next_model = try_next_model
        self.retry_after_s = retry_after_s
        self.metadata = metadata or {}


def classify_http_error(status: int, message: str, headers: dict[str, str] | None = None, metadata: dict[str, Any] | None = None) -> OpenRouterError:
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    lowered = message.lower()
    retry_after = _retry_after_seconds(headers)
    if status == 400:
        category = ProviderErrorCategory.PROVIDER_SCHEMA_INVALID if ("schema" in lowered or "response_format" in lowered) else ProviderErrorCategory.PROVIDER_REQUEST_INVALID
        return OpenRouterError(message, status=status, category=category, retryable=False, try_next_model=True, metadata=metadata)
    if status == 401:
        return OpenRouterError(message, status=status, category=ProviderErrorCategory.PROVIDER_AUTHENTICATION_FAILED, retryable=False, try_next_model=False, metadata=metadata)
    if status == 402:
        return OpenRouterError(message, status=status, category=ProviderErrorCategory.PROVIDER_QUOTA_EXCEEDED, retryable=False, try_next_model=False, metadata=metadata)
    if status == 403:
        return OpenRouterError(message, status=status, category=ProviderErrorCategory.PROVIDER_CONTENT_FILTERED, retryable=False, try_next_model=False, metadata=metadata)
    if status == 404:
        return OpenRouterError(message, status=status, category=ProviderErrorCategory.PROVIDER_MODEL_UNAVAILABLE, retryable=False, try_next_model=True, metadata=metadata)
    if status == 408:
        return OpenRouterError(message, status=status, category=ProviderErrorCategory.PROVIDER_TIMEOUT, retryable=True, try_next_model=True, metadata=metadata)
    if status == 429:
        short = retry_after is None or retry_after <= MAX_RATE_LIMIT_WAIT_S
        return OpenRouterError(message, status=status, category=ProviderErrorCategory.PROVIDER_RATE_LIMITED, retryable=short, try_next_model=True, retry_after_s=retry_after, metadata=metadata)
    if status == 503:
        # "No available provider meeting requirements": with
        # require_parameters this means no endpoint honours our parameters.
        return OpenRouterError(message, status=status, category=ProviderErrorCategory.PROVIDER_MODEL_UNAVAILABLE, retryable=False, try_next_model=True, metadata=metadata)
    if status in {500, 502, 504}:
        category = ProviderErrorCategory.PROVIDER_TIMEOUT if status == 504 else ProviderErrorCategory.PROVIDER_INTERNAL_ERROR
        return OpenRouterError(message, status=status, category=category, retryable=True, try_next_model=True, metadata=metadata)
    return OpenRouterError(message, status=status, category=ProviderErrorCategory.PROVIDER_INTERNAL_ERROR, retryable=False, try_next_model=True, metadata=metadata)


def _retry_after_seconds(headers: dict[str, str]) -> float | None:
    value = headers.get("retry-after")
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            pass
    reset = headers.get("x-ratelimit-reset")
    if reset:
        try:
            reset_ms = float(reset)
            # OpenRouter reports the reset as a Unix timestamp in milliseconds.
            return max(0.0, reset_ms / 1000.0 - time.time())
        except ValueError:
            pass
    return None


@dataclass(frozen=True)
class ModelCapabilities:
    model_id: str
    context_length: int | None = None
    is_free: bool = False
    supported_parameters: frozenset[str] = frozenset()
    known: bool = True

    @classmethod
    def from_catalog_entry(cls, entry: dict[str, Any]) -> "ModelCapabilities":
        pricing = entry.get("pricing") or {}
        model_id = str(entry.get("id", ""))
        is_free = model_id.endswith(":free") or (str(pricing.get("prompt")) == "0" and str(pricing.get("completion")) == "0")
        return cls(
            model_id=model_id,
            context_length=entry.get("context_length"),
            is_free=is_free,
            supported_parameters=frozenset(entry.get("supported_parameters") or []),
        )

    @classmethod
    def unknown(cls, model_id: str) -> "ModelCapabilities":
        return cls(model_id=model_id, is_free=model_id.endswith(":free"), known=False)

    def supports(self, parameter: str) -> bool:
        return parameter in self.supported_parameters

    def output_mode(self) -> OutputMode:
        # An unknown model (catalog unreachable) is asked for strict JSON
        # schema; require_parameters makes OpenRouter refuse endpoints that
        # cannot honour it rather than silently ignoring the schema.
        if not self.known or self.supports("structured_outputs"):
            return "json_schema"
        if self.supports("response_format"):
            return "json_object"
        return "prompt_only"


@dataclass
class ChatResult:
    content: str
    model: str
    upstream_provider: str | None
    generation_id: str | None
    finish_reason: str | None
    usage: dict[str, Any] = field(default_factory=dict)
    latency_s: float = 0.0


class OpenRouterClient:
    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = OPENROUTER_BASE_URL,
        timeout_s: float = 60.0,
        transport: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self._transport = transport

    def _client(self, timeout_s: float | None = None):
        import httpx

        headers = {"X-Title": APP_TITLE, "Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        timeout = httpx.Timeout(timeout_s or self.timeout_s, connect=min(15.0, timeout_s or self.timeout_s))
        return httpx.Client(base_url=self.base_url, headers=headers, timeout=timeout, transport=self._transport)

    def list_models(self) -> list[dict[str, Any]]:
        data = self._get("/models", authenticated=False)
        models = data.get("data")
        if not isinstance(models, list):
            raise OpenRouterError("Model catalog response had no data list.", status=None, category=ProviderErrorCategory.PROVIDER_INTERNAL_ERROR, retryable=True, try_next_model=False)
        return models

    def key_info(self) -> dict[str, Any]:
        """Zero-cost credential check; also reports free-tier daily usage."""
        data = self._get("/key", authenticated=True)
        return data.get("data", data)

    def chat(self, body: dict[str, Any], *, timeout_s: float | None = None) -> ChatResult:
        import httpx

        t0 = time.perf_counter()
        limit_s = timeout_s or self.timeout_s
        try:
            with self._client(timeout_s) as client:
                # httpx timeouts only bound the gap between bytes, and
                # OpenRouter keeps slow generations alive with whitespace, so
                # the body is streamed and the wall-clock limit enforced here.
                with client.stream("POST", "/chat/completions", content=json.dumps(body)) as streamed:
                    chunks: list[bytes] = []
                    for chunk in streamed.iter_bytes():
                        chunks.append(chunk)
                        if time.perf_counter() - t0 > limit_s:
                            raise OpenRouterError(
                                f"OpenRouter request exceeded {limit_s:.0f} s.",
                                status=None,
                                category=ProviderErrorCategory.PROVIDER_TIMEOUT,
                                retryable=False,
                                try_next_model=True,
                            )
                    # iter_bytes() has already undone any Content-Encoding (gzip,
                    # br); rebuilding with those headers would decode twice.
                    headers = {k: v for k, v in streamed.headers.items() if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
                    response = httpx.Response(streamed.status_code, headers=headers, content=b"".join(chunks))
        except httpx.TimeoutException as exc:
            raise OpenRouterError(f"OpenRouter request timed out: {exc}", status=None, category=ProviderErrorCategory.PROVIDER_TIMEOUT, retryable=True, try_next_model=True) from exc
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter network error: {exc}", status=None, category=ProviderErrorCategory.PROVIDER_NETWORK_ERROR, retryable=True, try_next_model=False) from exc
        latency = time.perf_counter() - t0
        data = self._decode(response)
        # OpenRouter may return HTTP 200 whose body carries only an error
        # (upstream failure after headers were sent).
        if isinstance(data.get("error"), dict):
            raise self._error_from_body(response.status_code if response.status_code >= 400 else 502, data["error"], dict(response.headers))
        choices = data.get("choices") or []
        if not choices:
            raise OpenRouterError("OpenRouter response contained no choices.", status=response.status_code, category=ProviderErrorCategory.PROVIDER_INTERNAL_ERROR, retryable=True, try_next_model=True)
        choice = choices[0]
        if isinstance(choice.get("error"), dict):
            raise self._error_from_body(502, choice["error"], dict(response.headers))
        message = choice.get("message") or {}
        if message.get("refusal"):
            raise OpenRouterError(f"Model refused: {message.get('refusal')}", status=response.status_code, category=ProviderErrorCategory.PROVIDER_REFUSAL, retryable=False, try_next_model=True)
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        return ChatResult(
            content=content or "",
            model=str(data.get("model") or body.get("model")),
            upstream_provider=data.get("provider"),
            generation_id=data.get("id"),
            finish_reason=choice.get("finish_reason"),
            usage=data.get("usage") or {},
            latency_s=latency,
        )

    def _get(self, path: str, *, authenticated: bool) -> dict[str, Any]:
        import httpx

        if authenticated and not self.api_key:
            raise OpenRouterError("OpenRouter API key is unavailable.", status=401, category=ProviderErrorCategory.PROVIDER_AUTHENTICATION_FAILED, retryable=False, try_next_model=False)
        try:
            with self._client(min(self.timeout_s, 30.0)) as client:
                response = client.get(path)
        except httpx.TimeoutException as exc:
            raise OpenRouterError(f"OpenRouter request timed out: {exc}", status=None, category=ProviderErrorCategory.PROVIDER_TIMEOUT, retryable=True, try_next_model=False) from exc
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter network error: {exc}", status=None, category=ProviderErrorCategory.PROVIDER_NETWORK_ERROR, retryable=True, try_next_model=False) from exc
        data = self._decode(response)
        if isinstance(data.get("error"), dict):
            raise self._error_from_body(response.status_code, data["error"], dict(response.headers))
        return data

    def _decode(self, response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            error = data.get("error") if isinstance(data, dict) else None
            if not isinstance(error, dict):
                error = {"message": response.text[:500] or f"HTTP {response.status_code}"}
            raise self._error_from_body(response.status_code, error, dict(response.headers))
        if not isinstance(data, dict):
            raise OpenRouterError("OpenRouter returned a non-object JSON body.", status=response.status_code, category=ProviderErrorCategory.PROVIDER_INTERNAL_ERROR, retryable=True, try_next_model=True)
        return data

    def _error_from_body(self, status: int, error: dict[str, Any], headers: dict[str, str]) -> OpenRouterError:
        code = error.get("code")
        if isinstance(code, int) and 400 <= code < 600:
            status = code
        message = str(error.get("message") or f"HTTP {status}")
        metadata = error.get("metadata") if isinstance(error.get("metadata"), dict) else {}
        raw = metadata.get("raw") if metadata else None
        if raw:
            message = f"{message} ({str(raw)[:300]})"
        return classify_http_error(status, message, headers, metadata)


class ModelCatalog:
    """OpenRouter model catalog with a small on-disk cache."""

    def __init__(self, client: OpenRouterClient, *, cache_path: Path | None = None, ttl_s: float = CATALOG_TTL_S) -> None:
        self.client = client
        self.cache_path = cache_path
        self.ttl_s = ttl_s
        self._entries: dict[str, dict[str, Any]] | None = None
        self.fetched_at: str | None = None
        self.last_error: str | None = None

    def entries(self) -> dict[str, dict[str, Any]]:
        if self._entries is not None:
            return self._entries
        cached = self._read_cache()
        if cached is not None:
            self._entries = cached
            return cached
        try:
            models = self.client.list_models()
        except Exception as exc:
            self.last_error = redact_secrets(exc)
            stale = self._read_cache(ignore_ttl=True)
            self._entries = stale or {}
            return self._entries
        self._entries = {str(m.get("id")): m for m in models if m.get("id")}
        self.fetched_at = datetime.now(timezone.utc).isoformat()
        self._write_cache(self._entries)
        return self._entries

    def capabilities(self, model_id: str) -> ModelCapabilities:
        entry = self.entries().get(model_id)
        if entry is None:
            return ModelCapabilities.unknown(model_id)
        return ModelCapabilities.from_catalog_entry(entry)

    def is_listed(self, model_id: str) -> bool | None:
        entries = self.entries()
        if not entries:
            return None
        return model_id in entries

    def free_structured_models(self) -> list[ModelCapabilities]:
        caps = [ModelCapabilities.from_catalog_entry(e) for e in self.entries().values()]
        return sorted(
            (c for c in caps if c.is_free and c.supports("structured_outputs") and c.model_id != "openrouter/free"),
            key=lambda c: c.model_id,
        )

    def cached_entries(self) -> dict[str, dict[str, Any]]:
        """Entries from the on-disk cache (even if stale); never touches the network."""
        return self._read_cache(ignore_ttl=True) or {}

    def _read_cache(self, *, ignore_ttl: bool = False) -> dict[str, dict[str, Any]] | None:
        if self.cache_path is None or not self.cache_path.exists():
            return None
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
            if not ignore_ttl and time.time() - float(payload.get("saved_at_epoch", 0)) > self.ttl_s:
                return None
            self.fetched_at = payload.get("fetched_at")
            return payload.get("models") or None
        except Exception:
            return None

    def _write_cache(self, entries: dict[str, dict[str, Any]]) -> None:
        if self.cache_path is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"saved_at_epoch": time.time(), "fetched_at": self.fetched_at, "models": entries}
            self.cache_path.write_text(json.dumps(payload), encoding="utf-8")
        except OSError:
            pass
