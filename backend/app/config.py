"""Runtime configuration. Every tunable comes from the environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = BACKEND_DIR / ".runtime"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    app_name: str = "NutriLens API"
    version: str = "0.1.0"
    debug: bool = False
    api_prefix: str = "/api"
    backend_port: int = 8010
    cors_origins: str = "http://localhost:5183,http://127.0.0.1:5183"

    # --- image limits ---
    max_upload_mb: float = 10.0
    max_image_edge: int = 1600
    jpeg_quality: int = 85

    # --- multi-image budget ---
    # Prefill cost grows roughly linearly with image count, so more images means
    # a smaller per-image edge. See README §10 for the measured numbers.
    max_images: int = 4
    multi_image_max_edge: int = 1024
    max_total_upload_mb: float = 20.0

    # --- database ---
    database_url: str = ""

    # --- llm ---
    llm_provider: str = "auto"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_model: str = "qwen-vl-max-latest"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 60.0
    llm_max_tokens: int = 2048
    llm_temperature: float = 0.2
    llm_enable_thinking: bool = False
    llm_thinking_param: str = "enable_thinking"
    llm_json_mode: bool = True
    llm_request_usage: bool = True

    # --- recognition ---
    low_confidence_threshold: float = 0.55

    # --- conversations ---
    #: How many recent messages to replay to the model. The first analysis is
    #: always included on top of these, since it anchors the whole conversation.
    max_history_turns: int = 8
    max_turn_text_chars: int = 1000

    # ---- derived ----
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)

    @property
    def max_total_upload_bytes(self) -> int:
        return int(self.max_total_upload_mb * 1024 * 1024)

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{(RUNTIME_DIR / 'nutrilens.db').as_posix()}"

    @property
    def llm_configured(self) -> bool:
        """True when a real API key is present. Drives demo-mode banners."""
        return bool(self.llm_api_key.strip())

    @property
    def resolved_provider(self) -> str:
        """Which provider the factory will actually pick."""
        choice = self.llm_provider.strip().lower()
        if choice == "auto":
            return "openai_compat" if self.llm_configured else "mock"
        if choice == "openai_compat" and not self.llm_configured:
            # Explicitly asked for the real thing but no key: fail loudly at
            # startup rather than silently serving fake data.
            raise ValueError(
                "LLM_PROVIDER=openai_compat 但未设置 LLM_API_KEY。"
                "请在 backend/.env 中填入 Key，或改用 LLM_PROVIDER=auto/mock。"
            )
        return choice

    @property
    def demo_mode(self) -> bool:
        return self.resolved_provider == "mock"


@lru_cache
def get_settings() -> Settings:
    return Settings()
