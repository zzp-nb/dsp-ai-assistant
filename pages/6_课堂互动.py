"""Student classroom-question submission and private processing status."""

from __future__ import annotations

import time

import streamlit as st

from ui.content import format_local_time, render_citations
from ui.guard import render_shell, setup_page
from ui.runtime import current_identity, services
from ui.theme import footer, page_header


setup_page("课堂互动")
render_shell()
page_header(
    "CLASSROOM INTERACTION",
    "课堂互动",
    "把问题交给课堂，而不是自动打上大屏。教师会在管理面板中选择问题，并决定是否展示 AI 回答。",
)

ctx = services()
db = ctx.db
identity = current_identity()

if identity.role == "teacher":
    st.info("教师请前往“教师管理 → 课堂问题”选择并展示问题。本页展示的是当前会话提交的问题。")
    st.page_link("pages/7_教师管理.py", label="打开教师管理 →")

ask_col, info_col = st.columns([2.2, 0.9], gap="large")
with info_col:
    st.markdown("#### 处理流程")
    st.markdown(
        "1. 你提交问题\n\n2. 问题进入教师待处理列表\n\n3. 教师选择问题\n\n4. 教师决定是否展示 AI 回答"
    )
    st.divider()
    st.markdown("#### 提示")
    st.caption("问题越具体越好：写清楚章节、概念和你卡住的地方。")
    st.page_link("pages/8_课堂展示.py", label="查看课堂大屏 →")

with ask_col:
    with st.form("classroom_question_form", border=True):
        question = st.text_area(
            "向课堂提问",
            height=120,
            max_chars=500,
            placeholder="例如：为什么频域采样会在时域产生周期延拓？我还是不理解这个对应关系。",
        )
        submitted = st.form_submit_button("提交给教师", type="primary", width="stretch")
    if submitted:
        question = question.strip()
        now = time.time()
        if len(question) < 5:
            st.warning("请把问题写得更具体一些（至少 5 个字符）。")
        elif (
            question == st.session_state.get("last_class_question")
            and now - float(st.session_state.get("last_class_time", 0)) < 20
        ):
            st.warning("这个问题刚刚提交过，请等待教师处理。")
        else:
            question_id = db.add_classroom_question(
                session_id=identity.session_token,
                student_key_value=identity.quota_key,
                student_name=identity.public_label,
                question=question,
            )
            st.session_state["last_class_question"] = question
            st.session_state["last_class_time"] = now
            st.success(f"问题已提交（编号 #{question_id}）。它不会自动投影，等待教师选择。")

st.divider()
st.markdown("### 我的问题")


@st.fragment(run_every="5s")
def render_my_questions() -> None:
    questions = db.list_classroom_questions_for_session(identity.session_token, limit=20)
    if not questions:
        st.caption("还没有提交过问题。讲师处理后可在这里看到状态。")
        return
    for item in questions:
        status = item["status"]
        if item["is_displayed"]:
            label = "正在课堂展示"
            css = ""
        elif status == "answered":
            label = "教师已生成回答（尚未公开）"
            css = "dsp-badge-muted"
        elif status == "archived":
            label = "已归档"
            css = "dsp-badge-muted"
        else:
            label = "等待教师处理"
            css = "dsp-badge-warm"
        with st.container(border=True):
            st.markdown(
                f'<span class="dsp-badge {css}">#{item["id"]} · {label}</span>'
                f'<span style="color:#8493A8;font-size:0.78rem;margin-left:0.5rem">'
                f'{format_local_time(item["created_at"])}</span>',
                unsafe_allow_html=True,
            )
            st.markdown(f"**{item['question']}**")
            if item["is_displayed"] and item["show_ai_answer"] and item["ai_answer"]:
                st.markdown("---")
                st.markdown("**课堂 AI 回答**")
                st.markdown(item["ai_answer"])
                render_citations(item["ai_citations"])
            elif item["is_displayed"]:
                st.caption("问题已展示到课堂；教师当前选择不展示 AI 回答。")
            elif status == "answered":
                st.caption("教师已处理该问题，但尚未选择在课堂公开展示。")
            else:
                st.caption("问题已进入教师面板，请耐心等待。")


render_my_questions()
st.caption("状态每 5 秒自动刷新一次。你也可以切换页面后再回来。")
footer()
