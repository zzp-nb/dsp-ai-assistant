"""Strict validation for AI-generated quizzes."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

TYPE_LABELS = {
    "single_choice": "单项选择题",
    "multiple_choice": "多项选择题",
    "fill_blank": "填空题",
    "true_false": "判断题",
    "calculation": "计算题",
    "short_answer": "简答题",
}
LABEL_TO_TYPE = {label: key for key, label in TYPE_LABELS.items()}
ALLOWED_DIFFICULTIES = {"基础", "中等", "提高"}
CHOICE_TYPES = {"single_choice", "multiple_choice"}


class QuizValidationError(ValueError):
    pass


@dataclass
class Quiz:
    title: str
    questions: list[dict[str, Any]] = field(default_factory=list)


def extract_json_object(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise QuizValidationError("未找到 JSON 对象")
    candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # A single trailing comma is common and safe to repair.
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise QuizValidationError(f"JSON 语法错误：{exc.msg}") from exc
    if not isinstance(data, dict):
        raise QuizValidationError("JSON 根节点必须是对象")
    return data


def _normalise_option(text: str, index: int) -> str:
    value = str(text).strip()
    prefix = chr(ord("A") + index)
    if re.match(rf"^{prefix}[\.\、\:：]\s*", value):
        return value
    return f"{prefix}. {value}"


def _normalise_answer(question_type: str, answer: Any, options: list[str]) -> str:
    text = str(answer).strip()
    if question_type == "single_choice":
        upper = text.upper().strip()
        match = re.search(r"\b([A-D])\b", upper)
        if not match:
            raise QuizValidationError("单选题答案必须是 A/B/C/D")
        return match.group(1)
    if question_type == "multiple_choice":
        letters = sorted(set(re.findall(r"[A-D]", text.upper())))
        if len(letters) < 2:
            raise QuizValidationError("多选题答案至少包含两个选项")
        return ",".join(letters)
    if question_type == "true_false":
        if text in {"正确", "对", "True", "true", "√"}:
            return "正确"
        if text in {"错误", "错", "False", "false", "×"}:
            return "错误"
        raise QuizValidationError("判断题答案必须是“正确”或“错误”")
    if not text:
        raise QuizValidationError("答案不能为空")
    return text


def validate_quiz(
    raw: str | dict[str, Any],
    *,
    expected_count: int,
    allowed_types: list[str],
) -> Quiz:
    data = extract_json_object(raw) if isinstance(raw, str) else raw
    questions_raw = data.get("questions")
    if not isinstance(questions_raw, list):
        raise QuizValidationError("questions 必须是数组")
    if len(questions_raw) != expected_count:
        raise QuizValidationError(f"题目数量为 {len(questions_raw)}，要求为 {expected_count}")
    allowed = [LABEL_TO_TYPE.get(item, item) for item in allowed_types]
    questions: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    for index, item in enumerate(questions_raw, start=1):
        if not isinstance(item, dict):
            raise QuizValidationError(f"第 {index} 题不是对象")
        raw_type = str(item.get("type", "")).strip()
        question_type = LABEL_TO_TYPE.get(raw_type, raw_type)
        if question_type not in TYPE_LABELS:
            raise QuizValidationError(f"第 {index} 题题型无效：{raw_type}")
        if allowed and question_type not in allowed:
            raise QuizValidationError(f"第 {index} 题题型不在用户选择范围内")
        question = str(item.get("question", "")).strip()
        if len(question) < 5:
            raise QuizValidationError(f"第 {index} 题题干过短")
        fingerprint = re.sub(r"\s+", "", question)[:80]
        if fingerprint in seen_questions:
            raise QuizValidationError(f"第 {index} 题与前面题目重复")
        seen_questions.add(fingerprint)

        raw_options = item.get("options", [])
        if raw_options is None:
            raw_options = []
        if not isinstance(raw_options, list):
            raise QuizValidationError(f"第 {index} 题 options 必须是数组")
        if question_type in CHOICE_TYPES:
            if len(raw_options) != 4:
                raise QuizValidationError(f"第 {index} 题选择题必须有 4 个选项")
            options = [_normalise_option(option, option_index) for option_index, option in enumerate(raw_options)]
        elif question_type == "true_false":
            options = ["正确", "错误"]
        else:
            options = []

        answer = _normalise_answer(question_type, item.get("answer", ""), options)
        explanation = str(item.get("explanation", "")).strip()
        if len(explanation) < 10:
            raise QuizValidationError(f"第 {index} 题缺少有效解析")
        difficulty = str(item.get("difficulty", "")).strip()
        if difficulty not in ALLOWED_DIFFICULTIES:
            difficulty = "中等"
        chapter = str(item.get("chapter", "")).strip()
        questions.append(
            {
                "id": index,
                "type": question_type,
                "type_label": TYPE_LABELS[question_type],
                "question": question,
                "options": options,
                "answer": answer,
                "explanation": explanation,
                "difficulty": difficulty,
                "chapter": chapter,
            }
        )
    title = str(data.get("title", "DSP 章节练习")).strip() or "DSP 章节练习"
    present_types = {item["type"] for item in questions}
    if allowed and expected_count >= len(allowed):
        missing = [TYPE_LABELS[item] for item in allowed if item not in present_types]
        if missing:
            raise QuizValidationError("缺少用户选择的题型：" + "、".join(missing))
    return Quiz(title=title, questions=questions)


def quiz_to_markdown(quiz: Quiz, *, include_answers: bool = True) -> str:
    lines = [f"# {quiz.title}", ""]
    for item in quiz.questions:
        lines.append(f"## {item['id']}. [{item['type_label']} · {item['difficulty']}]")
        lines.append(item["question"])
        for option in item["options"]:
            lines.append(f"- {option}")
        if include_answers:
            lines.extend(
                [
                    "",
                    f"**参考答案：** {item['answer']}",
                    "",
                    f"**解析：** {item['explanation']}",
                ]
            )
        lines.append("")
    return "\n".join(lines)
