"""
Per-organization AI provider configuration.

Each organization can plug in ONE active LLM provider used for:
  - Alert summaries (short human-readable text on each alert)
  - Daily / weekly report summaries (operational insights)

Computer-vision detection is INTENTIONALLY NOT routed through this. People
counting, object detection, and tracking always run in the CV worker
(`cv_worker/`) using OpenCV + YOLO. This model only controls LLM/text AI.

API keys are encrypted at rest with the same Fernet key used for RTSP URLs
(`FIELD_ENCRYPTION_KEY`). They are NEVER returned in API responses.
"""
from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel
from apps.common.security import decrypt_str, encrypt_str
from apps.organizations.models import Organization


class AIProviderSetting(TimeStampedModel):
    class ProviderType(models.TextChoices):
        DISABLED = "disabled", "Disabled (no AI)"
        OPENROUTER = "openrouter", "OpenRouter"
        OPENAI_COMPATIBLE = "openai_compatible", "OpenAI-compatible API"
        LOCAL_OLLAMA = "local_ollama", "Local Ollama"
        SELF_HOSTED = "self_hosted", "Self-hosted (OpenAI-compatible)"

    organization = models.OneToOneField(
        Organization,
        on_delete=models.CASCADE,
        related_name="ai_provider",
    )
    provider_type = models.CharField(
        max_length=32,
        choices=ProviderType.choices,
        default=ProviderType.DISABLED,
    )
    display_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Friendly name shown in the dashboard.",
    )
    base_url = models.URLField(
        blank=True,
        help_text=(
            "OpenRouter:  https://openrouter.ai/api/v1\n"
            "Ollama:      http://ollama:11434  (or http://host.docker.internal:11434)\n"
            "Self-hosted: your OpenAI-compatible endpoint, e.g. http://vllm:8000/v1"
        ),
    )
    model_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="e.g. openrouter/auto, openai/gpt-4o-mini, llama3.1:8b, qwen2.5:7b",
    )
    # Encrypted at rest. Always exposed write-only via the serializer.
    api_key_encrypted = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "AI provider setting"
        verbose_name_plural = "AI provider settings"

    def __str__(self) -> str:
        return f"{self.organization.name} → {self.get_provider_type_display()}"

    # --- API-key helpers (mirror Camera.rtsp_url pattern) -----------------
    @property
    def api_key(self) -> str:
        return decrypt_str(self.api_key_encrypted)

    @api_key.setter
    def api_key(self, value: str) -> None:
        self.api_key_encrypted = encrypt_str(value or "")

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key_encrypted)

    @property
    def masked_api_key(self) -> str:
        """Return a safe display string like 'sk-or-****abcd' or '' when unset."""
        raw = self.api_key
        if not raw:
            return ""
        if len(raw) <= 8:
            return "****"
        return f"{raw[:6]}****{raw[-4:]}"
