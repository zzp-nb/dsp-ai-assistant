"""AI question answering with three explanation modes and RAG citations."""

from __future__ import annotations

import hashlib
import time

import streamlit as st

from core.ai_service import friendly_error
from core.limits import get_runtime_limits
from core.prompts import MODE_NAMES
from ui.content import empty_state, quota_hint, render_citations
from ui.guard import render_shell, setup_page
from ui.runtime import current_identity, services
from ui.theme import footer, note, page_header


setup_page("智能问答")
render_shell()
page_header(
    "AI QUESTION ANSWERING",
    "智能问答",
    "围绕《数字信号处理》课程提问。回答优先检索教师 PPT 与教材；若资料不足，会明确标注为 AI 补充。",
)

ctx = services()
config, db, rag, ai = ctx.config, ctx.db, ctx.rag, ctx.ai
identity = current_identity()
limits = get_runtime_limits(db, config)

qa_col, side_col = st.columns([2.35, 0.85], gap="large")

with side_col:
    st.markdown("#### 讲解模式")
    mode = st.radio(
        "选择讲解方式",
        MODE_NAMES,
        index=1,
        label_visibility="collapsed",
        key="qa_mode",
    )
    mode_desc = {
        "通俗解释": "用生活类比建立直觉，再对应到专业术语。",
        "专业解释": "规范定义、适用条件和概念对比。",
        "数学推导": "从定义出发，逐步写出关键公式。",
    }[mode]
    st.caption(mode_desc)
    st.divider()
    stats = rag.stats()
    st.markdown("#### 回答引擎")
    if config.use_offline:
        st.markdown(
            f'<span class="dsp-badge">本地知识库 · 离线</span>'
            f'<span class="dsp-badge dsp-badge-muted">{ai.offline.entry_count} 个主题</span>',
            unsafe_allow_html=True,
        )
        st.caption("不联网、不调用 API、不产生 Token 费用。")
        st.page_link("pages/2_课程知识库.py", label="浏览内置知识库 →")
    else:
        st.markdown(
            '<span class="dsp-badge">DeepSeek · 在线</span>',
            unsafe_allow_html=True,
        )
        st.caption("每次回答会计入班级 API 额度。")
    st.divider()
    st.markdown("#### 课程资料状态")
    if stats["ready"]:
        st.markdown(
            f'<span class="dsp-badge">已索引 {stats["chunks"]} 个文本块</span>',
            unsafe_allow_html=True,
        )
        st.caption(f"来自 {stats['materials']} 份资料。回答下方可展开页码依据。")
    else:
        st.caption("未导入课程资料；离线回答将使用内置 DSP 知识库。")
        st.page_link("pages/2_课程知识库.py", label="前往课程知识库 →")
    st.divider()
    if config.use_offline:
        st.caption("离线模式不消耗 API 额度。")
    elif identity.role == "student":
        quota_hint(db, identity, config)
    else:
        st.caption("教师预览也使用统一 AI 服务，并计入班级总调用量。")
    if st.button("清空本次对话", width="stretch"):
        db.clear_chat_messages(identity.session_token, "qa")
        st.session_state.pop("qa_history", None)
        st.rerun()

with qa_col:
    if "qa_history" not in st.session_state:
        st.session_state["qa_history"] = db.get_chat_messages(identity.session_token, "qa", limit=30)
    history = st.session_state["qa_history"]
    if not history:
        empty_state(
            "从一个具体问题开始",
            "例如：为什么采样频率要大于信号最高频率的两倍？",
        )
        st.write("")
        examples = [
            "什么是离散时间信号？",
            "为什么需要采样？",
            "什么是奈奎斯特采样定理？",
            "DFT 和 FFT 有什么区别？",
            "FIR 和 IIR 滤波器有什么区别？",
            "如何理解 Z 变换？",
        ]
        cols = st.columns(2)
        for index, example in enumerate(examples):
            with cols[index % 2]:
                if st.button(example, key=f"qa_example_{index}", width="stretch"):
                    st.session_state["qa_pending"] = example
                    st.rerun()
    else:
        for message in history:
            role = message.get("role", "assistant")
            with st.chat_message(role, avatar="👤" if role == "user" else "🤖"):
                st.markdown(str(message.get("content", "")))
                if message.get("citations"):
                    render_citations(message["citations"])
        st.write("")

    if config.use_offline:
        note(
            "当前为完全离线模式：回答来自内置 DSP 知识库，不访问网络，也不需要 DeepSeek API。"
            "如果你上传了课程资料，回答会同时引用资料原文。"
        )
    elif not config.api_configured:
        note(
            "服务端尚未配置 DeepSeek API Key，暂时无法调用在线模型。",
            warning=True,
        )

    question = st.chat_input(
        "输入你的 DSP 问题，支持连续追问…",
        max_chars=limits.max_input_chars,
        key="qa_chat_input",
    )
    pending = st.session_state.pop("qa_pending", None)
    question = question or pending

    if question:
        question = question.strip()
        fingerprint = hashlib.sha256(question.encode("utf-8")).hexdigest()[:16]
        now = time.time()
        if not config.api_configured and not config.use_offline:
            st.warning("尚未配置 DeepSeek API Key，暂时无法生成回答。请联系教师完成服务端配置。")
        elif (
            st.session_state.get("last_qa_fingerprint") == fingerprint
            and now - float(st.session_state.get("last_qa_time", 0)) < 8
        ):
            st.warning("这个问题刚刚已经提交过，请稍候或换个问法。")
        elif len(question) > limits.max_input_chars:
            st.error(f"问题过长，请控制在 {limits.max_input_chars} 个字符以内。")
        else:
            st.session_state["last_qa_fingerprint"] = fingerprint
            st.session_state["last_qa_time"] = now
            with st.chat_message("user", avatar="👤"):
                st.markdown(question)
            with st.chat_message("assistant", avatar="🤖"):
                with st.spinner("正在检索课程资料并生成回答…"):
                    try:
                        result = ai.answer_question(question, mode, identity, history=history)
                    except Exception as exc:
                        st.error(friendly_error(exc))
                    else:
                        history.append({"role": "user", "content": question, "citations": []})
                        history.append(
                            {
                                "role": "assistant",
                                "content": result.content,
                                "citations": result.citations,
                            }
                        )
                        st.session_state["qa_history"] = history[-30:]
                        st.rerun()

footer()
