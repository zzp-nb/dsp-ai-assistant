"""Projector-friendly classroom display. Refreshes from SQLite every 3 seconds."""

from __future__ import annotations

import html

import streamlit as st

from ui.content import format_local_time, render_citations
from ui.guard import render_shell, setup_page
from ui.runtime import services
from ui.theme import footer


setup_page("课堂展示", sidebar="collapsed")
render_shell()
ctx = services()
db = ctx.db

st.markdown(
    """
    <div style="display:flex;justify-content:space-between;align-items:flex-end;gap:1rem;
                margin-top:1.1rem;margin-bottom:1.2rem;padding-bottom:0.9rem;border-bottom:1px solid #DDE5EF">
      <div>
        <div style="color:#2A9D8F;font-size:0.74rem;letter-spacing:0.15em;font-weight:700">CLASSROOM DISPLAY</div>
        <div style="font-size:1.6rem;font-weight:760;color:#172033;margin-top:0.2rem">课堂展示</div>
      </div>
      <div style="color:#8493A8;font-size:0.8rem">由教师控制 · 每 3 秒刷新</div>
    </div>
    """,
    unsafe_allow_html=True,
)


@st.fragment(run_every="3s")
def projected_question() -> None:
    current = db.get_displayed_question()
    if not current:
        st.markdown(
            """
            <div class="dsp-display-wrap" style="display:flex;align-items:center;justify-content:center;text-align:center">
              <div>
                <div style="font-size:2.3rem;color:#12355B;font-weight:700;margin-bottom:0.7rem">课堂展示待开始</div>
                <div style="font-size:1.05rem;color:#6B7A90;line-height:1.8">
                  学生在“课堂互动”提交的问题不会自动上屏。<br>
                  教师在“教师管理”中选择问题并点击“展示到课堂”后，这里才会显示。
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <div class="dsp-display-wrap">
          <div style="display:flex;justify-content:space-between;gap:1rem;color:#8493A8;font-size:0.82rem;margin-bottom:1.2rem">
            <span>问题 #{current["id"]} · 匿名同学提问</span>
            <span>{format_local_time(current["created_at"])}</span>
          </div>
          <div class="dsp-question">{html.escape(current["question"])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")
    if current["show_ai_answer"] and current["ai_answer"]:
        with st.container(border=True):
            st.markdown(
                '<span class="dsp-badge">AI 助教回答</span>',
                unsafe_allow_html=True,
            )
            st.markdown(current["ai_answer"])
            if current["ai_citations"]:
                with st.expander("资料来源", expanded=False):
                    render_citations(current["ai_citations"])
    else:
        st.markdown(
            '<div class="dsp-note" style="font-size:1rem">教师当前选择只展示问题，不展示 AI 回答。</div>',
            unsafe_allow_html=True,
        )


projected_question()
st.caption("本页仅展示教师明确选择的问题。若内容未更新，请等待 3 秒或刷新浏览器。")
footer()
