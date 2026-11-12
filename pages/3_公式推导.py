"""Step-by-step DSP formula derivation."""

from __future__ import annotations

import hashlib
import time

import streamlit as st

from core.ai_service import friendly_error
from core.limits import get_runtime_limits
from ui.content import quota_hint, render_ai_result
from ui.guard import render_shell, setup_page
from ui.runtime import current_identity, services
from ui.theme import footer, note, page_header


setup_page("公式推导")
render_shell()
page_header(
    "STEP-BY-STEP DERIVATION",
    "公式推导",
    "不只给结论：先解释符号，再说明意义，按步骤推导，最后用具体例子检查理解，并指出常见错误。",
)

ctx = services()
config, db, rag, ai = ctx.config, ctx.db, ctx.rag, ctx.ai
identity = current_identity()
limits = get_runtime_limits(db, config)
chapters = list(dict.fromkeys([*rag.chapters(), *ai.offline_chapters()]))

EXAMPLES = [
    "离散时间傅里叶变换 DTFT 的定义与收敛条件",
    "从 DFT 定义推导循环卷积定理",
    "FFT 的蝶形运算为什么能减少计算量",
    "Z 变换的收敛域如何判断",
    "奈奎斯特采样定理与频谱搬移",
    "FIR 滤波器线性相位的条件",
]

if "formula_result" not in st.session_state:
    st.session_state["formula_result"] = None
if "formula_topic" not in st.session_state:
    st.session_state["formula_topic"] = ""

input_col, help_col = st.columns([2.3, 0.9], gap="large")
with help_col:
    st.markdown("#### 推导范围")
    st.caption("DTFT、DFT/FFT、Z 变换、卷积、LTI 系统、采样定理、FIR/IIR 都可以。")
    st.markdown("#### 输出结构")
    st.markdown(
        "1. 公式与符号\n\n2. 物理/数学意义\n\n3. 分步推导\n\n4. 具体例子\n\n5. 常见错误"
    )
    st.divider()
    if config.use_offline:
        st.markdown(
            f'<span class="dsp-badge">本地知识库 · 离线</span>',
            unsafe_allow_html=True,
        )
        st.caption(f"{ai.offline.entry_count} 个内置主题，不调用 API。")
    elif identity.role == "student":
        quota_hint(db, identity, config)
    chapter_options = ["自动判断", *chapters]
    chapter = st.selectbox("优先检索章节（可选）", chapter_options)
    if not rag.stats()["ready"]:
        if config.use_offline:
            note("没有上传课程资料时，推导使用内置 DSP 知识库。")
        else:
            note("知识库尚无索引，推导将主要依据 AI 知识，并明确标注。", warning=True)

with input_col:
    with st.form("formula_form", border=True):
        topic = st.text_area(
            "输入公式、概念或推导请求",
            value=st.session_state["formula_topic"],
            height=130,
            max_chars=limits.max_input_chars,
            placeholder="例如：请从定义出发推导 DFT 的循环卷积定理，并说明与线性卷积的关系。",
        )
        submitted = st.form_submit_button("开始分步推导", type="primary", width="stretch")
    st.caption("示例：")
    example_cols = st.columns(2)
    for index, example in enumerate(EXAMPLES):
        with example_cols[index % 2]:
            if st.button(example, key=f"formula_example_{index}", width="stretch"):
                st.session_state["formula_topic"] = example
                st.session_state["formula_pending"] = example
                st.rerun()

    pending = st.session_state.pop("formula_pending", None)
    if submitted:
        topic = topic.strip()
    else:
        topic = pending or ""
    if topic and not config.api_configured and not config.use_offline:
        note("服务端尚未配置 DeepSeek API Key，暂时无法生成推导。", warning=True)
    elif topic:
        fingerprint = hashlib.sha256(topic.encode("utf-8")).hexdigest()[:16]
        now = time.time()
        if (
            st.session_state.get("formula_fingerprint") == fingerprint
            and now - float(st.session_state.get("formula_time", 0)) < 6
        ):
            st.warning("相同请求刚刚提交过，请稍候。")
        else:
            st.session_state["formula_fingerprint"] = fingerprint
            st.session_state["formula_time"] = now
            st.session_state["formula_topic"] = topic
            with st.spinner("正在检索资料并组织分步推导…"):
                try:
                    result = ai.derive_formula(
                        topic,
                        identity,
                        chapter=None if chapter == "自动判断" else chapter,
                    )
                except Exception as exc:
                    st.error(friendly_error(exc))
                else:
                    st.session_state["formula_result"] = result
                    st.session_state["formula_chapter"] = chapter

    result = st.session_state.get("formula_result")
    if result is not None:
        st.divider()
        headings = result.content.count("\n## ")
        if headings < 4:
            st.warning("本次回答的章节结构不完整，可能缺少推导步骤。建议重新生成或缩小问题范围。")
        render_ai_result(result, show_usage=identity.role == "teacher", expanded_sources=True)
        st.download_button(
            "下载本次推导（Markdown）",
            data=result.content,
            file_name="DSP公式推导.md",
            mime="text/markdown",
        )
        st.caption("提示：公式推导可能有多种等价路径；请重点核对每一步使用的定义和适用条件。")

footer()
