"""Application configuration.

Secrets are read from environment variables first, then Streamlit Secrets.
They are never sent to the browser or written into logs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from core.paths import PROJECT_ROOT, data_dir, database_path, materials_dir, vector_store_dir

DEFAULT_PRICING: dict[str, Any] = {
    "currency": "CNY",
    "version": "2025-09-29",
    "source": "https://api-docs.deepseek.com/quick_start/pricing",
    "note": "示例默认价，仅用于费用估算；请以 DeepSeek 官网当期价格为准，并修改 config/pricing.json。",
    "models": {
        "deepseek-chat": {
            "input_cache_hit_cny_per_million": 0.2,
            "input_cache_miss_cny_per_million": 2.0,
            "output_cny_per_million": 3.0,
        },
        "deepseek-flash": {
            "input_cache_hit_cny_per_million": 0.2,
            "input_cache_miss_cny_per_million": 2.0,
            "output_cny_per_million": 3.0,
        },
        "deepseek-reasoner": {
            "input_cache_hit_cny_per_million": 0.2,
            "input_cache_miss_cny_per_million": 2.0,
            "output_cny_per_million": 3.0,
        },
    },
}


def _streamlit_secret(name: str) -> str | None:
    """Read one Streamlit secret without failing outside a Streamlit runtime."""

    try:
        import streamlit as st

        value = st.secrets.get(name)
        if value is None:
            return None
        return str(value)
    except Exception:
        return None


def get_setting(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None and value != "":
        return value
    return _streamlit_secret(name) or default


def _get_bool(name: str, default: bool) -> bool:
    value = get_setting(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int, minimum: int = 0) -> int:
    value = get_setting(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _pricing_path() -> Path:
    configured = get_setting("DSP_PRICING_FILE")
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    return PROJECT_ROOT / "config" / "pricing.json"


@lru_cache(maxsize=1)
def load_pricing() -> dict[str, Any]:
    path = _pricing_path()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("models"), dict):
                return loaded
        except (OSError, json.JSONDecodeError):
            pass
    return DEFAULT_PRICING


@dataclass(frozen=True)
class AppConfig:
    app_name: str = "DSP AI 智能教学助手"
    class_password: str = field(default="", repr=False)
    teacher_password: str = field(default="", repr=False)
    deepseek_api_key: str = field(default="", repr=False)
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    request_timeout_seconds: int = 90
    max_input_chars: int = 1200
    max_output_tokens: int = 2400
    default_daily_student_limit: int = 30
    default_daily_global_limit: int = 300
    retrieval_top_k: int = 5
    min_retrieval_score: float = 0.12
    max_upload_mb: int = 30
    debug: bool = False
    offline_mode: bool = False
    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data")
    materials_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "course_materials")
    vector_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "vector_store")
    db_path: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "database" / "dsp.db")
    pricing: dict[str, Any] = field(default_factory=lambda: DEFAULT_PRICING)

    @property
    def auth_configured(self) -> bool:
        return bool(self.class_password and self.teacher_password)

    @property
    def api_configured(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def use_offline(self) -> bool:
        """Offline is explicit, or the automatic safe default when no key exists."""

        return self.offline_mode or not self.deepseek_api_key

    @property
    def setup_issues(self) -> list[str]:
        issues: list[str] = []
        if not self.class_password:
            issues.append("未配置班级访问密码（DSP_CLASS_PASSWORD）")
        if not self.teacher_password:
            issues.append("未配置教师密码（DSP_TEACHER_PASSWORD）")
        if self.class_password in {"class-demo-2026", "123456", "password"} or len(self.class_password) < 8:
            issues.append("班级密码仍是弱密码，请立即更换")
        if self.teacher_password in {"teacher-demo-2026", "123456", "password"} or len(self.teacher_password) < 8:
            issues.append("教师密码仍是弱密码，请立即更换")
        return issues

    @property
    def pricing_models(self) -> dict[str, Any]:
        models = self.pricing.get("models", {})
        return models if isinstance(models, dict) else {}


def load_config() -> AppConfig:
    base_url = (get_setting("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    return AppConfig(
        class_password=get_setting("DSP_CLASS_PASSWORD") or "",
        teacher_password=get_setting("DSP_TEACHER_PASSWORD") or "",
        deepseek_api_key=get_setting("DEEPSEEK_API_KEY") or "",
        deepseek_base_url=base_url,
        deepseek_model=get_setting("DEEPSEEK_MODEL") or "deepseek-chat",
        request_timeout_seconds=_get_int("DSP_REQUEST_TIMEOUT", 90, 10),
        max_input_chars=_get_int("DSP_MAX_INPUT_CHARS", 1200, 50),
        max_output_tokens=_get_int("DSP_MAX_OUTPUT_TOKENS", 2400, 100),
        default_daily_student_limit=_get_int("DSP_DAILY_STUDENT_LIMIT", 30, 1),
        default_daily_global_limit=_get_int("DSP_DAILY_GLOBAL_LIMIT", 300, 1),
        retrieval_top_k=_get_int("DSP_RETRIEVAL_TOP_K", 5, 1),
        min_retrieval_score=float(get_setting("DSP_MIN_RETRIEVAL_SCORE") or 0.12),
        max_upload_mb=_get_int("DSP_MAX_UPLOAD_MB", 30, 1),
        debug=_get_bool("DSP_DEBUG", False),
        offline_mode=_get_bool("DSP_OFFLINE_MODE", False),
        data_dir=data_dir(),
        materials_dir=materials_dir(),
        vector_dir=vector_store_dir(),
        db_path=database_path(),
        pricing=load_pricing(),
    )


def clear_config_cache() -> None:
    """Used by tests after changing environment variables."""

    load_pricing.cache_clear()
