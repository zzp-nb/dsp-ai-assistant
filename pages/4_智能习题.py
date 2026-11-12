"""AI-generated DSP exercises with validated answers and explanations."""

from __future__ import annotations

import hashlib
import re
import time

import streamlit as st

from core.ai_service import friendly_error
from core.quiz import TYPE_LABELS, quiz_to_markdown
from ui.content import quota_hint, render_citations
from ui.guard import render_shell, setup_page
from ui.runtime import current_identity, services
from ui.theme import footer, note, page_header


setup_page("智能习题")
render_shell()
page_header(
    "PRACTICE GENERATOR",
    "智能习题",
    "按章节、题型和难度生成练习。每题都带参考答案与解析；系统会校验题目数量、题型和答案格式，避免题答错位。",
)

ctx = services()
config, db, rag, ai = ctx.config, ctx.db, ctx.rag, ctx.ai
identity = current_identity()

DEFAULT_CHAPTERS = [
    "第1章 离散时间信号与系统",
    "第2章 采样与重建",
    "第3章 Z 变换",
    "第4章 离散傅里叶变换",
    "第5章 FIR 数字滤波器",
    "第6章 IIR 数字滤波器",
    "第7章 数字滤波器结构",
    "第8章 多采样率处理",
    "第9章 DSP 应用",
]
chapters = list(dict.fromkeys([*rag.chapters(), *ai.offline_chapters()]))
if not chapters:
    chapters = DEFAULT_CHAPTERS
chapters = ["全部章节", *chapters, "自定义主题"]

with st.form("quiz_form", border=True):
    col1, col2, col3 = st.columns([1.2, 1.5, 0.8])
    with col1:
        chapter = st.selectbox("章节 / 主题", chapters)
        difficulty = st.select_slider("难度", options=["基础", "中等", "提高"], value="中等")
    with col2:
        type_labels = st.multiselect(
            "题型（可多选）",
            list(TYPE_LABELS.values()),
            default=["单项选择题", "计算题"],
        )
        custom_chapter = ""
        if chapter == "自定义主题":
            custom_chapter = st.text_input("输入自定义主题", placeholder="例如：窗函数法设计 FIR 低通滤波器")
    with col3:
        count = st.number_input("题目数量", min_value=1, max_value=10, value=3)
        st.write("")
        generate = st.form_submit_button("生成习题", type="primary", width="stretch")

type_keys = [key for key, label in TYPE_LABELS.items() if label in type_labels]
target_chapter = custom_chapter.strip() if chapter == "自定义主题" else chapter
if chapter == "自定义主题" and not custom_chapter.strip() and generate:
    st.warning("请输入自定义主题。")
elif not type_keys and generate:
    st.warning("请至少选择一种题型。")
elif generate and not config.api_configured and not config.use_offline:
    note("服务端尚未配置 DeepSeek API Key，暂时无法生成习题。", warning=True)
elif generate:
    raw_key = f"{target_chapter}|{','.join(type_keys)}|{difficulty}|{int(count)}"
    fingerprint = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
    now = time.time()
    if (
        st.session_state.get("quiz_fingerprint") == fingerprint
        and now - float(st.session_state.get("quiz_time", 0)) < 8
    ):
        st.warning("相同设置刚刚生成过，请稍候再试。")
    else:
        st.session_state["quiz_fingerprint"] = fingerprint
        st.session_state["quiz_time"] = now
        spinner_text = (
            "正在从本地题库抽题并校验…"
            if config.use_offline
            else "正在检索章节内容、生成并校验题目…"
        )
        with st.spinner(spinner_text):
            try:
                result = ai.generate_quiz(
                    chapter=target_chapter,
                    types=type_keys,
                    difficulty=difficulty,
                    count=int(count),
                    identity=identity,
                    extra=custom_chapter,
                )
            except Exception as exc:
                st.error(friendly_error(exc))
            else:
                st.session_state["quiz_result"] = result
                st.session_state["quiz_meta"] = {
                    "chapter": target_chapter,
                    "difficulty": difficulty,
                    "count": int(count),
                    "types": list(type_labels),
                }
                st.success("已生成并通过结构校验。请先独立作答，再展开答案。")

if config.use_offline:
    st.caption("本地题库生成，不调用 API，不消耗 Token。")
elif identity.role == "student":
    quota_hint(db, identity, config)
else:
    st.caption("教师预览会消耗一次班级 AI 调用额度。")

result = st.session_state.get("quiz_result")
meta = st.session_state.get("quiz_meta")
if result is not None and result.quiz is not None:
    quiz = result.quiz
    st.divider()
    head_col, meta_col = st.columns([2, 1])
    with head_col:
        st.markdown(f"### {quiz.title}")
    with meta_col:
        st.caption(
            f"{meta.get('chapter', '')} · {meta.get('difficulty', '')} · {len(quiz.questions)} 题"
            if meta
            else f"{len(quiz.questions)} 题"
        )
    render_citations(result.citations)
    if result.notice:
        st.info(result.notice)
    if not result.grounded:
        if config.use_offline:
            note("本地题库没有找到完全匹配的题，请调整章节、题型或难度。", warning=True)
        else:
            note("本次出题未检索到直接相关的课程资料，题目主要依据 AI 补充知识。", warning=True)

    for item in quiz.questions:
        with st.container(border=True):
            st.markdown(
                f'<span class="dsp-badge">{item["type_label"]}</span>'
                f'<span class="dsp-badge dsp-badge-muted">{item["difficulty"]}</span>'
                f'<span class="dsp-badge dsp-badge-muted">{item["chapter"] or "未标注章节"}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(f"**{item['id']}.** {item['question']}")
            for option in item["options"]:
                st.markdown(f"- {option}")
            with st.expander("查看参考答案与解析"):
                st.markdown(f"**参考答案：** {item['answer']}")
                st.markdown(f"**解析：** {item['explanation']}")
    safe_title = re.sub(r'[\\/:*?"<>|]+', "_", quiz.title)[:60] or "DSP练习"
    st.download_button(
        "下载本次习题与答案（Markdown）",
        data=quiz_to_markdown(quiz),
        file_name=f"DSP习题_{safe_title}.md",
        mime="text/markdown",
    )
    st.caption(
        "系统已校验：题目数量、题型、选项数量与答案格式。生成式 AI 仍可能出错，"
        "若发现题答不一致，请把题目反馈给教师。"
    )

footer()
