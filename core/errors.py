"""Typed application errors that are safe to show to learners."""

from __future__ import annotations


class DSPAssistantError(Exception):
    """Base class with a Chinese, user-facing message."""

    code = "app_error"
    user_message = "系统暂时不可用，请稍后再试。"

    def __init__(self, message: str | None = None, *, debug_detail: str = ""):
        self.user_message = message or self.user_message
        self.debug_detail = debug_detail
        super().__init__(self.user_message)


class ConfigurationError(DSPAssistantError):
    code = "configuration_error"
    user_message = "服务端尚未完成配置，请联系教师。"


class DeepSeekError(DSPAssistantError):
    code = "deepseek_error"
    user_message = "AI 服务暂时不可用，请稍后再试。"

    def __init__(
        self,
        message: str | None = None,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        debug_detail: str = "",
    ):
        super().__init__(message, debug_detail=debug_detail)
        self.status_code = status_code
        self.retryable = retryable


class QuotaExceeded(DSPAssistantError):
    code = "quota_exceeded"
    user_message = "今日 AI 调用额度已用完，请联系教师或明天再试。"


class InvalidAIResponse(DSPAssistantError):
    code = "invalid_ai_response"
    user_message = "AI 返回的内容格式不正确，请重试一次。"
