"""Offline DSP tutor powered by bundled knowledge and question banks.

No network access, API key or external embedding service is used here.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np

from core.embedding import HashingTfidfEmbedder, analyze_terms
from core.quiz import Quiz, quiz_to_markdown, validate_quiz
from knowledge import ENTRIES, QUIZ_BANK


class OfflineTutorError(Exception):
    pass


@dataclass
class OfflineHit:
    entry: dict[str, Any]
    score: float


@dataclass
class OfflineAnswer:
    content: str
    citations: list[dict[str, Any]] = field(default_factory=list)
    grounded: bool = False
    notice: str = ""
    entry: dict[str, Any] | None = None


@dataclass
class OfflineQuizResult:
    quiz: Quiz
    notice: str = ""


def _mathify(text: str) -> str:
    """Wrap common DSP variable names in inline math for readable prose."""

    if not text or "$" in text:
        return text
    terms = [
        "N_x+N_h-1",
        "f_s/(2M)",
        "f_s/2",
        "2f_m",
        "f_s/N",
        "x_a(t)",
        "x_a(nT_s)",
        "T_s=1/f_s",
        "f_s=1/T_s",
        "x[n]",
        "h[n]",
        "y[n]",
        "X(z)",
        "H(z)",
        "Y(z)",
        "W_N",
        "f_s",
        "f_m",
        "f_N",
        "T_s",
        "N_x",
        "N_h",
        "B_x",
        "a_k",
        "b_k",
        "b_m",
        "Lf_s",
    ]
    result = text
    for term in sorted(terms, key=len, reverse=True):
        pattern = rf"(?<![A-Za-z0-9_$]){re.escape(term)}(?![A-Za-z0-9_$])"
        result = re.sub(pattern, f"${term}$", result)
    return result


def _entry_text(entry: dict[str, Any]) -> str:
    pieces = [
        entry.get("title", ""),
        entry.get("chapter", ""),
        " ".join(entry.get("aliases", [])),
        entry.get("summary", ""),
        entry.get("professional", ""),
        entry.get("intuition", ""),
        " ".join(entry.get("key_points", [])),
        " ".join(entry.get("derivation", [])),
        entry.get("example", ""),
        " ".join(entry.get("common_mistakes", [])),
    ]
    for formula in entry.get("formulas", []):
        pieces.append(formula.get("latex", ""))
        pieces.append(formula.get("meaning", ""))
    return "\n".join(str(piece) for piece in pieces if piece)


class OfflineTutor:
    def __init__(self, entries: list[dict[str, Any]] | None = None):
        self.entries = entries or ENTRIES
        self._texts = [_entry_text(entry) for entry in self.entries]
        self._term_counts = [self._counts(text) for text in self._texts]
        self._doc_len = [sum(counts.values()) for counts in self._term_counts]
        self._avgdl = sum(self._doc_len) / max(1, len(self._doc_len))
        self._df: dict[str, int] = {}
        for counts in self._term_counts:
            for term in counts:
                self._df[term] = self._df.get(term, 0) + 1
        self._embedder = HashingTfidfEmbedder(dim=1024).fit(self._texts)
        self._matrix = self._embedder.transform(self._texts)

    @staticmethod
    def _counts(text: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for term in analyze_terms(text):
            counts[term] = counts.get(term, 0) + 1
        return counts

    @property
    def entry_count(self) -> int:
        return len(self.entries)

    def chapters(self) -> list[str]:
        return sorted({entry["chapter"] for entry in self.entries})

    def topic_titles(self) -> list[str]:
        return [entry["title"] for entry in self.entries]

    def _keyword_scores(self, query: str) -> np.ndarray:
        query_counts = self._counts(query)
        scores = np.zeros(len(self.entries), dtype=np.float32)
        if not query_counts:
            return scores
        total_docs = len(self.entries)
        k1, b = 1.5, 0.75
        for index, doc_counts in enumerate(self._term_counts):
            length = self._doc_len[index] or 1
            score = 0.0
            for term, query_tf in query_counts.items():
                tf = doc_counts.get(term, 0)
                if not tf:
                    continue
                df = self._df.get(term, 0)
                idf = math.log(1.0 + (total_docs - df + 0.5) / (df + 0.5))
                denominator = tf + k1 * (1 - b + b * length / max(self._avgdl, 1e-9))
                score += idf * (tf * (k1 + 1) / denominator) * min(query_tf, 3)
            scores[index] = score
        return scores

    def search(self, query: str, *, top_k: int = 3, min_score: float = 0.12) -> list[OfflineHit]:
        query = (query or "").strip()
        if not query:
            return []
        query_vector = self._embedder.transform([query])[0]
        vector_scores = self._matrix @ query_vector
        keyword = self._keyword_scores(query)
        normalized_keyword = keyword / float(keyword.max()) if float(keyword.max()) > 0 else keyword
        combined = 0.62 * vector_scores + 0.38 * normalized_keyword

        normalised = query.lower().replace(" ", "")
        for index, entry in enumerate(self.entries):
            aliases = [alias.lower().replace(" ", "") for alias in entry.get("aliases", [])]
            title = entry["title"].lower().replace(" ", "")
            if title and (title in normalised or normalised in title):
                combined[index] += 0.45
            elif any(alias and (alias in normalised or normalised in alias) for alias in aliases):
                combined[index] += 0.28

        hits: list[OfflineHit] = []
        for index in np.argsort(combined)[::-1]:
            score = float(combined[index])
            if score < min_score:
                break
            hits.append(OfflineHit(entry=self.entries[int(index)], score=round(score, 4)))
            if len(hits) >= max(1, top_k):
                break
        return hits

    @staticmethod
    def _builtin_citation(entry: dict[str, Any], marker: str = "资料1") -> dict[str, Any]:
        return {
            "marker": marker,
            "source": "DSP 内置知识库",
            "location": f"条目：{entry['title']}",
            "chapter": entry["chapter"],
            "doc_type": "builtin",
            "snippet": entry["summary"][:240],
        }

    def _course_section(self, course_hits: list[Any] | None) -> tuple[str, list[dict[str, Any]]]:
        if not course_hits:
            return "", []
        lines = ["", "### 课程资料中的相关段落"]
        citations: list[dict[str, Any]] = []
        for index, hit in enumerate(course_hits[:2], start=2):
            chunk = hit.chunk if hasattr(hit, "chunk") else None
            if chunk is None:
                continue
            citation = hit.citation
            citation["marker"] = f"资料{index}"
            citations.append(citation)
            lines.append(
                f"- **《{chunk.source_name}》** {chunk.page_label}："
                f"{chunk.text[:260].replace(chr(10), ' ')}…"
            )
        return "\n".join(lines), citations

    def _fallback(self, query: str) -> OfflineAnswer:
        suggestions = "、".join(self.topic_titles()[:10])
        content = (
            "### 本地知识库暂未直接匹配\n\n"
            "当前是**离线模式**，没有调用任何网络服务。"
            "本地知识库主要覆盖以下主题：\n\n"
            f"{suggestions}\n\n"
            "请换一个更具体的 DSP 术语或问题；如果你上传了课程资料，"
            "也可以在“课程知识库”先建立索引，再按资料内容提问。"
        )
        return OfflineAnswer(
            content=content,
            citations=[],
            grounded=False,
            notice="本地知识库未找到足够直接的条目。",
        )

    def answer(
        self,
        question: str,
        mode: str = "专业解释",
        *,
        course_hits: list[Any] | None = None,
    ) -> OfflineAnswer:
        hits = self.search(question, top_k=2)
        course_block, course_citations = self._course_section(course_hits)
        if not hits:
            fallback = self._fallback(question)
            if course_citations:
                fallback.content += "\n\n" + course_block
                fallback.citations = course_citations
                fallback.grounded = True
            return fallback

        entry = hits[0].entry
        citations = [self._builtin_citation(entry), *course_citations]
        lines = [
            "> **本地知识库回答** · 未调用网络或 API",
            "",
            f"### {entry['title']}",
            "",
        ]
        if mode == "通俗解释":
            lines.extend(
                [
                    "**先建立直觉**",
                    _mathify(entry["intuition"]),
                    "",
                    "**核心结论**",
                    _mathify(entry["summary"]),
                    "",
                    "**关键点**",
                    *[f"- {_mathify(point)}" for point in entry["key_points"]],
                    "",
                ]
            )
        elif mode == "数学推导":
            lines.extend(
                [
                    "**结论与适用条件**",
                    _mathify(entry["professional"]),
                    "",
                    "**关键公式**",
                ]
            )
            if entry["formulas"]:
                for formula in entry["formulas"]:
                    lines.extend([f"$${formula['latex']}$$", f"- {_mathify(formula['meaning'])}"])
            else:
                lines.append("- 该主题以概念和应用为主，没有单独列出的核心公式。")
            lines.extend(["", "**推导思路**"])
            lines.extend(
                f"{index}. {_mathify(step)}" for index, step in enumerate(entry["derivation"], start=1)
            )
            lines.append("")
        else:
            lines.extend(
                [
                    "**规范解释**",
                    _mathify(entry["professional"]),
                    "",
                    "**关键点**",
                    *[f"- {_mathify(point)}" for point in entry["key_points"]],
                    "",
                ]
            )
            if entry["formulas"]:
                lines.append("**核心公式**")
                for formula in entry["formulas"]:
                    lines.extend([f"$${formula['latex']}$$", f"- {_mathify(formula['meaning'])}"])
                lines.append("")

        lines.extend(
            [
                "**例子**",
                _mathify(entry["example"]),
                "",
                "**常见错误**",
                *[f"- {_mathify(mistake)}" for mistake in entry["common_mistakes"]],
            ]
        )
        if course_block:
            lines.append(course_block)
        content = "\n".join(lines)
        return OfflineAnswer(
            content=content,
            citations=citations,
            grounded=True,
            entry=entry,
        )

    def derive(self, topic: str, *, course_hits: list[Any] | None = None) -> OfflineAnswer:
        hits = self.search(topic, top_k=1)
        course_block, course_citations = self._course_section(course_hits)
        if not hits:
            fallback = self._fallback(topic)
            fallback.content = fallback.content.replace("本地知识库暂未直接匹配", "本地知识库暂未收录该公式")
            return fallback
        entry = hits[0].entry
        citations = [self._builtin_citation(entry), *course_citations]
        lines = [
            "> **本地知识库推导** · 未调用网络或 API",
            "",
            f"### {entry['title']}",
            "",
            "## 1. 公式与符号含义",
        ]
        if entry["formulas"]:
            for formula in entry["formulas"]:
                lines.extend([f"$${formula['latex']}$$", f"- {_mathify(formula['meaning'])}"])
        else:
            lines.append("该主题没有单独列出的公式，下面解释其核心关系。")
        lines.extend(
            [
                "",
                "## 2. 物理/数学意义",
                _mathify(entry["professional"]),
                "",
                "## 3. 分步推导",
            ]
        )
        lines.extend(
            f"{index}. {_mathify(step)}" for index, step in enumerate(entry["derivation"], start=1)
        )
        lines.extend(
            [
                "",
                "## 4. 具体例子",
                _mathify(entry["example"]),
                "",
                "## 5. 常见错误",
                *[f"- {_mathify(mistake)}" for mistake in entry["common_mistakes"]],
            ]
        )
        if course_block:
            lines.append(course_block)
        return OfflineAnswer(
            content="\n".join(lines),
            citations=citations,
            grounded=True,
            entry=entry,
        )

    def quiz(
        self,
        *,
        chapter: str,
        types: list[str],
        difficulty: str,
        count: int,
    ) -> OfflineQuizResult:
        if count < 1:
            raise OfflineTutorError("题目数量必须大于 0。")
        if not types:
            raise OfflineTutorError("请至少选择一种题型。")
        if count < len(types):
            raise OfflineTutorError("题目数量不能少于所选题型数量。")

        all_questions = [dict(item) for item in QUIZ_BANK]
        chapter_pool = [
            item
            for item in all_questions
            if not chapter
            or chapter in {"全部章节", "自定义主题"}
            or chapter in item["chapter"]
            or item["chapter"] in chapter
        ]
        if not chapter_pool:
            chapter_pool = all_questions
        type_pool = [item for item in chapter_pool if item["type"] in types]
        if not type_pool:
            raise OfflineTutorError("本地题库中没有所选章节与题型的组合，请调整选择。")

        requested_difficulty = [item for item in type_pool if item["difficulty"] == difficulty]
        other_difficulty = [item for item in type_pool if item["difficulty"] != difficulty]
        all_chapter_any_difficulty = [
            item for item in all_questions if item["type"] in types and item["difficulty"] == difficulty
        ]
        all_any = [item for item in all_questions if item["type"] in types]
        notice = ""

        def pick_pool() -> list[dict]:
            nonlocal notice
            if len(requested_difficulty) >= count:
                return requested_difficulty
            if len(type_pool) >= count:
                notice = "本地题库该难度题量不足，已补充同章节其他难度题目。"
                return type_pool
            if len(all_chapter_any_difficulty) >= count:
                notice = "本地题库该章节题量不足，已补充其他章节同难度题目。"
                return all_chapter_any_difficulty
            if len(all_any) >= count:
                notice = "本地题库该章节题量不足，已补充其他章节题目。"
                return all_any
            raise OfflineTutorError(f"本地题库题量不足：当前最多可出 {len(all_any)} 题。")

        pool = pick_pool()
        # Ensure each selected type appears at least once when enough slots exist.
        selected: list[dict] = []
        used: set[int] = set()
        for question_type in types:
            for index, item in enumerate(pool):
                if index not in used and item["type"] == question_type:
                    selected.append(item)
                    used.add(index)
                    break
        for index, item in enumerate(pool):
            if len(selected) >= count:
                break
            if index not in used:
                selected.append(item)
                used.add(index)
        if len(selected) < count:
            raise OfflineTutorError(f"本地题库题量不足：当前只能生成 {len(selected)} 题。")

        payload = {
            "title": f"{chapter if chapter not in {'', '全部章节', '自定义主题'} else 'DSP'} · 本地题库",
            "questions": [
                {
                    "id": index,
                    "type": item["type"],
                    "question": item["question"],
                    "options": item.get("options", []),
                    "answer": item["answer"],
                    "explanation": item["explanation"],
                    "difficulty": item["difficulty"],
                    "chapter": item["chapter"],
                }
                for index, item in enumerate(selected[:count], start=1)
            ],
        }
        quiz = validate_quiz(payload, expected_count=count, allowed_types=types)
        return OfflineQuizResult(quiz=quiz, notice=notice)

    def quiz_markdown(self, quiz: Quiz) -> str:
        return quiz_to_markdown(quiz)


@lru_cache(maxsize=1)
def get_offline_tutor() -> OfflineTutor:
    return OfflineTutor()
