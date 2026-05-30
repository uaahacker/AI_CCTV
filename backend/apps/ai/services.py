"""
AI provider service layer.

Architecture
------------
- `BaseAIProvider`     — abstract interface.
- `OpenRouterProvider` / `OpenAICompatibleProvider` / `LocalOllamaProvider` /
  `SelfHostedProvider` — concrete implementations. All four use the
  OpenAI-compatible `POST /chat/completions` shape, since Ollama and most
  self-hosted runtimes (vLLM, LM Studio, text-generation-webui, llama.cpp
  server) speak it. The only differences are the default `base_url` and
  whether an API key is required.
- `DisabledProvider`   — safe fallback used when the org hasn't configured AI
  or `is_active=False`. Returns deterministic stub text instead of raising.
- `AIProviderFactory.for_organization(org)` — pick the right provider.

Public methods on every provider
--------------------------------
- `generate_alert_summary(alert_data: dict) -> str`
- `generate_daily_report_summary(report_data: dict) -> str`
- `test_connection() -> tuple[bool, str]`

All network calls are wrapped in a try/except that returns a safe fallback
string on failure — the dashboard must never crash because the LLM is down.
"""
from __future__ import annotations

import json
import logging
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

logger = logging.getLogger(__name__)

# Hard caps so a misconfigured provider can never hang a Celery worker or
# DRF request thread for too long.
HTTP_TIMEOUT_SECONDS = 20
MAX_OUTPUT_CHARS = 1200


# ---------------------------------------------------------------------------
# Base / fallback
# ---------------------------------------------------------------------------
class BaseAIProvider:
    """Abstract provider. Subclasses must implement `_chat`."""

    requires_api_key: bool = True
    default_base_url: str = ""

    def __init__(self, settings_obj):
        self.settings = settings_obj
        self.base_url = (settings_obj.base_url or self.default_base_url).rstrip("/")
        self.model = settings_obj.model_name or "openrouter/auto"
        self.api_key = settings_obj.api_key  # plaintext, only inside the process

    # --- Public API --------------------------------------------------------
    def generate_alert_summary(self, alert_data: dict[str, Any]) -> str:
        prompt = (
            "You are an operations assistant for a CCTV analytics platform. "
            "Write ONE short paragraph (max 60 words) summarising this alert "
            "in plain English for a non-technical site manager. Mention the "
            "camera, the metric, the threshold, and one possible cause.\n\n"
            f"Alert JSON:\n{json.dumps(alert_data, default=str)[:1500]}"
        )
        return self._safe_chat(prompt, fallback=_fallback_alert(alert_data))

    def generate_daily_report_summary(self, report_data: dict[str, Any]) -> str:
        prompt = (
            "You are an operations assistant. Given the following aggregate "
            "CCTV analytics for the period, write a concise executive summary "
            "(max 120 words). Cover: total people counted, busiest camera, "
            "peak hour, number of alerts, and one actionable insight. "
            "Do NOT invent numbers that are not in the data.\n\n"
            f"Report JSON:\n{json.dumps(report_data, default=str)[:3000]}"
        )
        return self._safe_chat(prompt, fallback=_fallback_report(report_data))

    def test_connection(self) -> tuple[bool, str]:
        try:
            out = self._chat("Reply with the single word: ok")
            return True, (out[:200] or "(empty response)")
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)[:300]

    # --- Internals ---------------------------------------------------------
    def _safe_chat(self, prompt: str, *, fallback: str) -> str:
        try:
            out = self._chat(prompt).strip()
            return out[:MAX_OUTPUT_CHARS] if out else fallback
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI provider %s failed: %s", self.__class__.__name__, exc)
            return fallback

    def _chat(self, prompt: str) -> str:  # pragma: no cover - subclasses override
        raise NotImplementedError


class DisabledProvider(BaseAIProvider):
    """No-op provider — returns deterministic fallback strings."""

    requires_api_key = False

    def __init__(self, settings_obj=None):
        # Don't touch real settings — we never call out.
        self.settings = settings_obj

    def generate_alert_summary(self, alert_data):
        return _fallback_alert(alert_data)

    def generate_daily_report_summary(self, report_data):
        return _fallback_report(report_data)

    def test_connection(self):
        return False, "AI is disabled for this organization."


# ---------------------------------------------------------------------------
# Concrete OpenAI-compatible providers
# ---------------------------------------------------------------------------
class _OpenAICompatibleBase(BaseAIProvider):
    """Shared `_chat` implementation using the OpenAI `/chat/completions` shape."""

    def _chat(self, prompt: str) -> str:
        if not self.base_url:
            raise RuntimeError("base_url is empty")
        if self.requires_api_key and not self.api_key:
            raise RuntimeError("api_key is missing")

        url = f"{self.base_url}/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a concise CCTV operations assistant."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 400,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "ai-cctv-analytics/1.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # OpenRouter recommends these headers for routing/billing attribution.
        if isinstance(self, OpenRouterProvider):
            headers["HTTP-Referer"] = "https://github.com/ai-cctv-analytics"
            headers["X-Title"] = "AI CCTV Analytics"

        req = urlrequest.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urlrequest.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
                body = resp.read().decode("utf-8", errors="replace")
        except urlerror.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}")
        except urlerror.URLError as e:
            raise RuntimeError(f"Network error: {e.reason}")

        data = json.loads(body)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            return ""


class OpenRouterProvider(_OpenAICompatibleBase):
    default_base_url = "https://openrouter.ai/api/v1"


class OpenAICompatibleProvider(_OpenAICompatibleBase):
    """Generic OpenAI-compatible endpoint — user supplies base_url + key."""
    default_base_url = "https://api.openai.com/v1"


class LocalOllamaProvider(_OpenAICompatibleBase):
    """Ollama exposes an OpenAI-compatible endpoint at /v1 since v0.1.30."""
    requires_api_key = False
    default_base_url = "http://ollama:11434/v1"


class SelfHostedProvider(_OpenAICompatibleBase):
    """vLLM, LM Studio, text-generation-webui, llama.cpp server, etc."""
    requires_api_key = False
    default_base_url = ""  # user must supply


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
_REGISTRY: dict[str, type[BaseAIProvider]] = {}


def _register():
    # Imported lazily to avoid a circular import at module load.
    from .models import AIProviderSetting

    _REGISTRY.update({
        AIProviderSetting.ProviderType.OPENROUTER: OpenRouterProvider,
        AIProviderSetting.ProviderType.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
        AIProviderSetting.ProviderType.LOCAL_OLLAMA: LocalOllamaProvider,
        AIProviderSetting.ProviderType.SELF_HOSTED: SelfHostedProvider,
        AIProviderSetting.ProviderType.DISABLED: DisabledProvider,
    })


class AIProviderFactory:
    @staticmethod
    def for_settings(settings_obj) -> BaseAIProvider:
        if not _REGISTRY:
            _register()
        if not settings_obj or not settings_obj.is_active:
            return DisabledProvider(settings_obj)
        cls = _REGISTRY.get(settings_obj.provider_type, DisabledProvider)
        if cls is DisabledProvider:
            return DisabledProvider(settings_obj)
        return cls(settings_obj)

    @staticmethod
    def for_organization(organization) -> BaseAIProvider:
        # Imported lazily so this module can be imported before Django apps load.
        from .models import AIProviderSetting

        try:
            cfg = AIProviderSetting.objects.get(organization=organization)
        except AIProviderSetting.DoesNotExist:
            return DisabledProvider(None)
        return AIProviderFactory.for_settings(cfg)


# ---------------------------------------------------------------------------
# Deterministic fallbacks — used when AI is disabled OR a call fails.
# ---------------------------------------------------------------------------
def _fallback_alert(alert_data: dict[str, Any]) -> str:
    title = alert_data.get("title", "Alert")
    severity = alert_data.get("severity", "warning")
    camera = alert_data.get("camera_name") or alert_data.get("camera") or "a camera"
    return f"[{severity.upper()}] {title} on {camera}."


def _fallback_report(report_data: dict[str, Any]) -> str:
    days = report_data.get("range_days", "?")
    per_cam = report_data.get("per_camera") or []
    busiest = per_cam[0].get("camera__name", "n/a") if per_cam else "n/a"
    total = sum((row.get("total") or 0) for row in per_cam)
    return (
        f"Last {days} day(s): {total} people counted across "
        f"{len(per_cam)} camera(s); busiest camera was '{busiest}'. "
        "Enable an AI provider in Settings → AI for richer insights."
    )
