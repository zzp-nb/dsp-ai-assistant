"""Reusable answer, citation and status rendering."""

from __future__ import annotations

import html
from datetime import datetime, timezone

import streamlit as st

from core.ai_service import AIResult
from core.cost_tracker import format_cny
from core.database import LOCAL_TZ, local_day_bounds_utc

DOC_TYPE_LABELS = {
    "pptx": "PPT",
    "pdf": "教材 PDF",
    "text": "补充文本",
    "builtin": "内置知识",
}


def format_local_time(iso_utc: str | None, *, include_date: bool = True) -> str:
    if not iso_utc:
        return "—"
    try:
        value = datetime.fromisoformat(iso_utc)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        local = value.astimezone(LOCAL_TZ)
        return local.strftime("%m-%d %H:%M" if include_date else "%H:%M")
    except ValueError:
        return iso_utc


def render_citations(citations: list[dict], *, expanded: bool = False) -> None:
    if not citations:
        return
    with st.expander(f"查看参考依据（{len(citations)} 条）", expanded=expanded):
        for item in citations:
            marker = html.escape(str(item.get("marker", "资料")))
            source = html.escape(str(item.get("source", "未知资料")))
            location = html.escape(str(item.get("location", "")))
            chapter = html.escape(str(item.get("chapter", "") or "未标注章节"))
            doc_type = DOC_TYPE_LABELS.get(str(item.get("doc_type", "")), "课程资料")
            snippet = html.escape(str(item.get("snippet", "")).strip())
            snippet = snippet.replace("\n", "<br>")
            st.markdown(
                f"""
                <div class="dsp-source">
                  <div class="dsp-source-top">
                    <span><span class="dsp-badge">{marker}</span>
                    <span class="dsp-source-name">{source}</span></span>
                    <span class="dsp-source-loc">{location}</span>
                  </div>
                  <div style="font-size:0.75rem;color:#8493A8;margin-top:0.25rem">
                    {html.escape(doc_type)} · {chapter}
                  </div>
                  <div class="dsp-source-snippet">{snippet}…</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.caption("以上为实际命中的本地资料/内置条目；位置由解析器或条目元数据记录，不由模型生成。")


def render_ai_result(
    result: AIResult,
    *,
    show_usage: bool = False,
    expanded_sources: bool = False,
) -> None:
    engine_label = "本地知识库 · 离线" if result.engine == "offline" else "DeepSeek"
    if result.engine == "offline":
        if result.grounded:
            st.markdown(
                f'<span class="dsp-badge">{html.escape(engine_label)}</span>'
                f'<span class="dsp-badge dsp-badge-muted">{html.escape(result.mode)}</span>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<span class="dsp-badge dsp-badge-warm">{html.escape(engine_label)} · 未命中</span>',
                unsafe_allow_html=True,
            )
    elif result.grounded:
        st.markdown(
            f'<span class="dsp-badge">已检索 {len(result.citations)} 条资料</span>'
            f'<span class="dsp-badge dsp-badge-muted">{html.escape(result.mode)}</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="dsp-badge dsp-badge-warm">未检索到直接资料 · AI 补充解释</span>',
            unsafe_allow_html=True,
        )
    if result.notice:
        st.info(result.notice)
    st.markdown(result.content)
    render_citations(result.citations, expanded=expanded_sources)
    if show_usage:
        if result.engine == "offline":
            st.caption("本地知识库回答，不消耗 Token、不调用 DeepSeek API。")
        else:
            st.caption(
                f"模型 {result.model or '—'} · 输入 {result.usage.get('prompt_tokens', 0)} tokens · "
                f"输出 {result.usage.get('completion_tokens', 0)} tokens · "
                f"估算费用 {format_cny(result.cost_cny) if result.cost_known else '价格未配置'}"
            )


def render_chat_history(messages: list[dict], *, show_usage: bool = False) -> None:
    for message in messages:
        role = message.get("role", "assistant")
        with st.chat_message(role, avatar="👤" if role == "user" else "🤖"):
            st.markdown(str(message.get("content", "")))
            citations = message.get("citations") or []
            if citations:
                render_citations(citations)


def status_badge(status: str) -> str:
    labels = {
        "pending": ("待处理", "dsp-badge-warm"),
        "answered": ("已生成回答", ""),
        "displayed": ("展示中", ""),
        "archived": ("已归档", "dsp-badge-muted"),
        "ready": ("已索引", ""),
        "empty": ("无文本", "dsp-badge-warm"),
        "error": ("解析失败", "dsp-badge-warm"),
    }
    label, css = labels.get(status, (status, "dsp-badge-muted"))
    return f'<span class="dsp-badge {css}">{html.escape(label)}</span>'


def empty_state(title: str, detail: str) -> None:
    st.markdown(
        f"""
        <div style="text-align:center;padding:3.2rem 1rem;border:1px dashed #C9D6E5;border-radius:16px;background:#FBFCFE">
          <div style="font-size:1.1rem;font-weight:650;color:#12355B">{html.escape(title)}</div>
          <div style="color:#6B7A90;font-size:0.88rem;margin-top:0.5rem">{html.escape(detail)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def quota_hint(db, identity, config) -> None:
    from core.limits import get_runtime_limits

    limits = get_runtime_limits(db, config)
    today_calls = db.count_calls_since(local_day_bounds_utc()[0], identity.quota_key)
    remaining = max(0, limits.daily_student_limit - today_calls)
    st.caption(
        f"今日剩余 AI 调用：{remaining} / {limits.daily_student_limit} 次"
        "（每次提问或生成计 1 次）"
    )
