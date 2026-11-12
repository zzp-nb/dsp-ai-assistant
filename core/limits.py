"""Runtime-configurable quotas and input limits."""

from __future__ import annotations

from dataclasses import dataclass

from core.config import AppConfig
from core.database import Database


@dataclass(frozen=True)
class RuntimeLimits:
    daily_student_limit: int
    daily_global_limit: int
    max_input_chars: int
    max_output_tokens: int


def get_runtime_limits(database: Database, config: AppConfig) -> RuntimeLimits:
    values = database.get_settings()
    return RuntimeLimits(
        daily_student_limit=_positive_int(values.get("daily_student_limit"), config.default_daily_student_limit),
        daily_global_limit=_positive_int(values.get("daily_global_limit"), config.default_daily_global_limit),
        max_input_chars=_positive_int(values.get("max_input_chars"), config.max_input_chars),
        max_output_tokens=_positive_int(values.get("max_output_tokens"), config.max_output_tokens),
    )


def _positive_int(value: object, fallback: int) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback
