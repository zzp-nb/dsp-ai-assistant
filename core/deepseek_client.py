"""DeepSeek chat API client.

DeepSeek exposes an OpenAI-compatible chat-completions endpoint. We call it
directly with requests so the server has a small dependency surface and full
control over error handling. The API key never leaves the server process.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import requests

from core.errors import ConfigurationError, DeepSeekError


@dataclass
class ChatResult:
    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cache_hit_tokens: int = 0
    cache_miss_tokens: int = 0
    latency_ms: int = 0
    request_id: str = ""
    raw_usage: dict[str, Any] = field(default_factory=dict)


class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        timeout_seconds: int = 90,
        session: requests.Session | None = None,
        max_retries: int = 2,
        retry_backoff: float = 0.8,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = max(10, int(timeout_seconds))
        self.session = session or requests.Session()
        self.max_retries = max(0, min(max_retries, 3))
        self.retry_backoff = retry_backoff

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.35,
        max_tokens: int = 1600,
        response_format: dict[str, str] | None = None,
    ) -> ChatResult:
        if not self.api_key:
            raise ConfigurationError("服务端未配置 DeepSeek API Key，请联系教师。")
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "temperature": max(0.0, min(float(temperature), 1.5)),
            "max_tokens": max(64, int(max_tokens)),
        }
        if response_format:
            payload["response_format"] = response_format

        last_error: DeepSeekError | None = None
        for attempt in range(self.max_retries + 1):
            started = time.monotonic()
            try:
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=(10, self.timeout_seconds),
                )
            except requests.Timeout as exc:
                last_error = DeepSeekError(
                    "AI 服务响应超时，请稍后重试。", retryable=True, debug_detail=str(exc)
                )
            except requests.RequestException as exc:
                last_error = DeepSeekError(
                    "无法连接 AI 服务，请检查网络后重试。",
                    retryable=True,
                    debug_detail=str(exc),
                )
            else:
                latency_ms = int((time.monotonic() - started) * 1000)
                if response.status_code == 200:
                    return self._parse_response(response, latency_ms)
                last_error = self._map_http_error(response)
                if not last_error.retryable:
                    raise last_error

            if attempt < self.max_retries:
                time.sleep(self.retry_backoff * (2**attempt))

        raise last_error or DeepSeekError("AI 服务调用失败，请稍后重试。")

    def _parse_response(self, response: requests.Response, latency_ms: int) -> ChatResult:
        try:
            data = response.json()
        except ValueError as exc:
            raise DeepSeekError("AI 服务返回了无法解析的数据。", debug_detail=str(exc)) from exc
        if not isinstance(data, dict):
            raise DeepSeekError("AI 服务返回格式异常。")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise DeepSeekError("AI 服务未返回有效回答。")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekError("AI 返回了空回答，请重试。")
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
        cache_hit = int(usage.get("prompt_cache_hit_tokens") or 0)
        cache_miss = int(usage.get("prompt_cache_miss_tokens") or max(0, prompt_tokens - cache_hit))
        return ChatResult(
            content=content.strip(),
            model=str(data.get("model") or self.model),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cache_hit_tokens=cache_hit,
            cache_miss_tokens=cache_miss,
            latency_ms=latency_ms,
            request_id=str(data.get("id") or ""),
            raw_usage=usage,
        )

    @staticmethod
    def _map_http_error(response: requests.Response) -> DeepSeekError:
        status = response.status_code
        detail = ""
        try:
            body = response.json()
            if isinstance(body, dict):
                error = body.get("error", body)
                detail = str(error.get("message") if isinstance(error, dict) else error)[:300]
        except ValueError:
            detail = (response.text or "")[:300]
        mapping = {
            400: ("请求参数有误，请缩短问题或稍后重试。", False),
            401: ("AI 服务认证失败，请联系教师检查 API Key。", False),
            402: ("AI 服务账户余额不足，请联系教师充值。", False),
            403: ("AI 服务拒绝访问，请联系教师检查账户权限。", False),
            429: ("AI 请求过于频繁，请稍等一分钟再试。", True),
            500: ("AI 服务内部错误，请稍后重试。", True),
            502: ("AI 服务网关异常，请稍后重试。", True),
            503: ("AI 服务繁忙，请稍后重试。", True),
            504: ("AI 服务响应超时，请稍后重试。", True),
        }
        message, retryable = mapping.get(status, (f"AI 服务调用失败（HTTP {status}）。", status >= 500))
        return DeepSeekError(message, status_code=status, retryable=retryable, debug_detail=detail)

    def test_connection(self) -> ChatResult:
        return self.chat(
            [
                {"role": "system", "content": "你是连接测试助手。只回复“连接成功”。"},
                {"role": "user", "content": "请回复：连接成功"},
            ],
            temperature=0.0,
            max_tokens=20,
        )
