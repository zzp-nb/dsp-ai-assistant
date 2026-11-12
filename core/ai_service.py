"""Application service that combines RAG, DeepSeek, quotas and cost logging."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from core.auth import LearnerIdentity
from core.config import AppConfig
from core.cost_tracker import CostTracker
from core.database import Database
from core.deepseek_client import ChatResult, DeepSeekClient
from core.errors import (
    ConfigurationError,
    DeepSeekError,
    DSPAssistantError,
    InvalidAIResponse,
    QuotaExceeded,
)
from core.limits import get_runtime_limits
from core.offline_tutor import OfflineAnswer, OfflineTutorError, get_offline_tutor
from core.prompts import (
    CLASSROOM_SYSTEM,
    FORMULA_SYSTEM,
    QUIZ_SYSTEM,
    classroom_prompt,
    formula_prompt,
    qa_system_prompt,
    qa_user_prompt,
    quiz_prompt,
)
from core.quiz import Quiz, QuizValidationError, validate_quiz
from core.rag_engine import RAGEngine, build_context


@dataclass
class AIResult:
    content: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    cost_cny: float = 0.0
    cost_known: bool = True
    model: str = ""
    latency_ms: int = 0
    grounded: bool = False
    mode: str = ""
    quiz: Quiz | None = None
    engine: str = "deepseek"
    notice: str = ""


class AIService:
    def __init__(
        self,
        config: AppConfig,
        database: Database,
        rag: RAGEngine | None = None,
        client: DeepSeekClient | None = None,
    ):
        self.config = config
        self.db = database
        self.rag = rag
        self.client = client
        self.cost_tracker = CostTracker(config.pricing)

    @property
    def offline(self):
        return get_offline_tutor()

    @property
    def is_offline(self) -> bool:
        return self.config.use_offline

    def offline_chapters(self) -> list[str]:
        return self.offline.chapters()

    def offline_topics(self) -> list[str]:
        return self.offline.topic_titles()

    def search_builtin(self, query: str, top_k: int = 5):
        return self.offline.search(query, top_k=top_k)

    def _offline_result(
        self,
        answer: OfflineAnswer,
        *,
        mode: str,
        quiz: Quiz | None = None,
        citations: list[dict[str, Any]] | None = None,
    ) -> AIResult:
        return AIResult(
            content=answer.content,
            citations=citations if citations is not None else answer.citations,
            usage={},
            cost_cny=0.0,
            cost_known=True,
            model="builtin-knowledge",
            latency_ms=0,
            grounded=answer.grounded,
            mode=mode,
            quiz=quiz,
            engine="offline",
            notice=answer.notice,
        )

    def _client(self) -> DeepSeekClient:
        if self.client is None:
            self.client = DeepSeekClient(
                self.config.deepseek_api_key,
                base_url=self.config.deepseek_base_url,
                model=self.config.deepseek_model,
                timeout_seconds=self.config.request_timeout_seconds,
            )
        return self.client

    def _retrieve(self, query: str, *, chapter: str | None = None, top_k: int | None = None):
        if self.rag is None:
            return []
        hits = self.rag.search(
            query,
            top_k=top_k or self.config.retrieval_top_k,
            chapter=chapter,
            min_score=self.config.min_retrieval_score,
        )
        if not hits and chapter:
            hits = self.rag.search(
                query,
                top_k=top_k or self.config.retrieval_top_k,
                min_score=self.config.min_retrieval_score,
            )
        return hits

    @staticmethod
    def _validate_input(text: str, max_chars: int, field_name: str = "问题") -> str:
        value = (text or "").strip()
        if not value:
            raise DSPAssistantError(f"请输入{field_name}。")
        if len(value) > max_chars:
            raise DSPAssistantError(f"{field_name}过长，请控制在 {max_chars} 个字符以内（当前 {len(value)} 字）。")
        return value

    def _run(
        self,
        *,
        messages: list[dict[str, str]],
        feature: str,
        session_id: str,
        quota_key: str,
        max_tokens: int,
        temperature: float = 0.35,
        response_format: dict[str, str] | None = None,
        teacher: bool = False,
    ) -> ChatResult:
        limits = get_runtime_limits(self.db, self.config)
        decision = self.db.reserve_api_call(
            session_id=session_id,
            student_key=quota_key,
            feature=feature,
            model=self.config.deepseek_model,
            student_limit=1_000_000 if teacher else limits.daily_student_limit,
            global_limit=limits.daily_global_limit,
        )
        if not decision.allowed:
            if decision.reason == "student_daily_limit":
                raise QuotaExceeded(
                    f"你今天的 AI 调用次数已达到上限（{limits.daily_student_limit} 次）。"
                    "明天会自动恢复；如有课堂急需，请联系教师。"
                )
            raise QuotaExceeded(
                "全班今日 AI 调用总量已达到教师设置的上限，请稍后再试或联系教师调整额度。"
            )

        assert decision.reservation_id is not None
        try:
            result = self._client().chat(
                messages,
                temperature=temperature,
                max_tokens=max(64, min(max_tokens, 4000)),
                response_format=response_format,
            )
        except DeepSeekError as exc:
            self.db.fail_api_call(
                decision.reservation_id,
                error_code=exc.code if exc.status_code is None else f"http_{exc.status_code}",
                error_message=exc.user_message,
            )
            raise
        except Exception as exc:
            self.db.fail_api_call(
                decision.reservation_id,
                error_code="internal_error",
                error_message=type(exc).__name__,
            )
            raise DeepSeekError("AI 服务调用出现异常，请稍后重试。", debug_detail=str(exc)) from exc

        cost = self.cost_tracker.estimate(
            result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cache_hit_tokens=result.cache_hit_tokens,
            cache_miss_tokens=result.cache_miss_tokens,
        )
        self.db.complete_api_call(
            decision.reservation_id,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            cache_hit_tokens=result.cache_hit_tokens,
            cache_miss_tokens=result.cache_miss_tokens,
            cost_cny=cost.cny,
            latency_ms=result.latency_ms,
            request_id=result.request_id,
        )
        result.cost_estimate = cost  # type: ignore[attr-defined]
        return result

    def answer_question(
        self,
        question: str,
        mode: str,
        identity: LearnerIdentity,
        history: list[dict[str, Any]] | None = None,
    ) -> AIResult:
        limits = get_runtime_limits(self.db, self.config)
        question = self._validate_input(question, limits.max_input_chars)
        hits = self._retrieve(question)
        if self.config.use_offline:
            answer = self.offline.answer(question, mode, course_hits=hits)
            self.db.add_chat_message(
                session_id=identity.session_token,
                feature="qa",
                role="user",
                content=question,
                mode=mode,
            )
            self.db.add_chat_message(
                session_id=identity.session_token,
                feature="qa",
                role="assistant",
                content=answer.content,
                mode=mode,
                citations=answer.citations,
            )
            return self._offline_result(answer, mode=mode)
        context, citations = build_context(hits)
        history_messages = self._history_messages(history or [])
        messages = [
            {"role": "system", "content": qa_system_prompt(mode, context, has_context=bool(hits))},
            *history_messages,
            {"role": "user", "content": qa_user_prompt(question)},
        ]
        result = self._run(
            messages=messages,
            feature="qa",
            session_id=identity.session_token,
            quota_key=identity.quota_key,
            max_tokens=limits.max_output_tokens,
            temperature=0.4,
        )
        self.db.add_chat_message(
            session_id=identity.session_token,
            feature="qa",
            role="user",
            content=question,
            mode=mode,
        )
        self.db.add_chat_message(
            session_id=identity.session_token,
            feature="qa",
            role="assistant",
            content=result.content,
            mode=mode,
            citations=citations,
        )
        return self._result(result, citations=citations, grounded=bool(hits), mode=mode)

    def derive_formula(
        self,
        topic: str,
        identity: LearnerIdentity,
        *,
        chapter: str | None = None,
    ) -> AIResult:
        limits = get_runtime_limits(self.db, self.config)
        topic = self._validate_input(topic, limits.max_input_chars, "公式或主题")
        hits = self._retrieve(topic, chapter=chapter, top_k=4)
        if self.config.use_offline:
            answer = self.offline.derive(topic, course_hits=hits)
            return self._offline_result(answer, mode="公式推导")
        context, citations = build_context(hits, max_chars=4200)
        messages = [
            {"role": "system", "content": FORMULA_SYSTEM},
            {"role": "user", "content": formula_prompt(topic, context)},
        ]
        result = self._run(
            messages=messages,
            feature="formula",
            session_id=identity.session_token,
            quota_key=identity.quota_key,
            max_tokens=min(2200, limits.max_output_tokens),
            temperature=0.25,
        )
        return self._result(result, citations=citations, grounded=bool(hits), mode="公式推导")

    def generate_quiz(
        self,
        *,
        chapter: str,
        types: list[str],
        difficulty: str,
        count: int,
        identity: LearnerIdentity,
        extra: str = "",
    ) -> AIResult:
        limits = get_runtime_limits(self.db, self.config)
        if not 1 <= count <= 10:
            raise DSPAssistantError("题目数量需在 1 到 10 之间。")
        if not types:
            raise DSPAssistantError("请至少选择一种题型。")
        if count < len(types):
            raise DSPAssistantError("题目数量不能少于所选题型数量。")
        if self.config.use_offline:
            try:
                generated = self.offline.quiz(
                    chapter=chapter,
                    types=types,
                    difficulty=difficulty,
                    count=count,
                )
            except OfflineTutorError as exc:
                raise DSPAssistantError(str(exc)) from exc
            answer = OfflineAnswer(
                content=generated.quiz.title,
                grounded=True,
                notice=generated.notice,
            )
            return self._offline_result(
                answer,
                mode="智能习题",
                quiz=generated.quiz,
                citations=[
                    {
                        "marker": "题库",
                        "source": "DSP 内置题库",
                        "location": generated.quiz.title,
                        "chapter": chapter,
                        "doc_type": "builtin",
                        "snippet": generated.notice or "按章节、题型和难度从本地题库抽题。",
                    }
                ],
            )
        query = f"{chapter} {' '.join(types)} {difficulty} 数字信号处理 练习"
        chapter_filter = chapter if chapter not in {"全部章节", "自定义主题"} else None
        hits = self._retrieve(query, chapter=chapter_filter, top_k=4)
        context, citations = build_context(hits, max_chars=4000)
        messages = [
            {"role": "system", "content": QUIZ_SYSTEM},
            {
                "role": "user",
                "content": quiz_prompt(
                    chapter=chapter,
                    types=types,
                    difficulty=difficulty,
                    count=count,
                    context=context,
                    extra=extra[:300],
                ),
            },
        ]
        result = self._run(
            messages=messages,
            feature="quiz",
            session_id=identity.session_token,
            quota_key=identity.quota_key,
            max_tokens=min(3500, limits.max_output_tokens),
            temperature=0.35,
            response_format={"type": "json_object"},
        )
        try:
            quiz = validate_quiz(result.content, expected_count=count, allowed_types=types)
        except QuizValidationError as exc:
            raise InvalidAIResponse(
                "AI 生成的题目结构不完整，本次未计入有效结果，请重新生成一次。",
                debug_detail=str(exc),
            ) from exc
        return self._result(result, citations=citations, grounded=bool(hits), mode="智能习题", quiz=quiz)

    def answer_classroom_question(self, question: str, teacher_session_id: str) -> AIResult:
        limits = get_runtime_limits(self.db, self.config)
        question = self._validate_input(question, min(limits.max_input_chars, 800))
        hits = self._retrieve(question, top_k=4)
        if self.config.use_offline:
            answer = self.offline.answer(question, "专业解释", course_hits=hits)
            return self._offline_result(answer, mode="课堂回答")
        context, citations = build_context(hits, max_chars=3800)
        messages = [
            {"role": "system", "content": CLASSROOM_SYSTEM},
            {"role": "user", "content": classroom_prompt(question, context)},
        ]
        result = self._run(
            messages=messages,
            feature="classroom",
            session_id=teacher_session_id,
            quota_key="teacher:classroom",
            max_tokens=min(900, limits.max_output_tokens),
            temperature=0.3,
            teacher=True,
        )
        return self._result(result, citations=citations, grounded=bool(hits), mode="课堂回答")

    def test_connection(self, teacher_session_id: str) -> AIResult:
        if self.config.use_offline:
            return AIResult(
                content="当前为本地离线模式，问答、推导和习题均使用内置 DSP 知识库，不需要连接 DeepSeek。",
                model="builtin-knowledge",
                grounded=False,
                mode="连接测试",
                engine="offline",
            )
        result = self._run(
            messages=[
                {"role": "system", "content": "你是连接测试助手。只回复“连接成功”。"},
                {"role": "user", "content": "请回复：连接成功"},
            ],
            feature="connection_test",
            session_id=teacher_session_id,
            quota_key="teacher:connection",
            max_tokens=20,
            temperature=0.0,
            teacher=True,
        )
        return self._result(result, citations=[], grounded=False, mode="连接测试")

    def _result(
        self,
        result: ChatResult,
        *,
        citations: list[dict[str, Any]],
        grounded: bool,
        mode: str,
        quiz: Quiz | None = None,
    ) -> AIResult:
        estimate = self.cost_tracker.estimate(
            result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            cache_hit_tokens=result.cache_hit_tokens,
            cache_miss_tokens=result.cache_miss_tokens,
        )
        return AIResult(
            content=result.content,
            citations=citations,
            usage={
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "total_tokens": result.total_tokens,
                "cache_hit_tokens": result.cache_hit_tokens,
            },
            cost_cny=estimate.cny,
            cost_known=estimate.known_price,
            model=result.model,
            latency_ms=result.latency_ms,
            grounded=grounded,
            mode=mode,
            quiz=quiz,
        )

    @staticmethod
    def _history_messages(history: list[dict[str, Any]]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for item in history[-6:]:
            role = item.get("role")
            content = str(item.get("content", "")).strip()
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content[:1800]})
        return messages


def friendly_error(exc: Exception) -> str:
    if isinstance(exc, DSPAssistantError):
        return exc.user_message
    if isinstance(exc, ConfigurationError):
        return exc.user_message
    return "系统出现异常，请稍后重试；若持续出现请联系教师。"


def contains_unsafe_html(text: str) -> bool:
    return bool(re.search(r"<\s*(script|iframe|object|embed)\b", text or "", re.IGNORECASE))
