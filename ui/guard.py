"""Page-level access guards and shared sidebar."""

from __future__ import annotations

import streamlit as st

from ui.runtime import current_identity, session_code
from ui.theme import inject_css, sidebar_navigation


def setup_page(title: str, *, layout: str = "wide", sidebar: str = "auto") -> None:
    st.set_page_config(
        page_title=f"{title} · DSP AI 智能教学助手",
        page_icon="◫",
        layout=layout,
        initial_sidebar_state=sidebar,
    )
    inject_css()


def require_login(*, teacher_only: bool = False) -> None:
    """Stop rendering when the browser session has not passed a password gate."""

    if not st.session_state.get("authenticated"):
        st.error("请先通过班级或教师入口登录，再访问该页面。")
        if st.button("返回登录页", type="primary"):
            st.switch_page("app.py")
        st.stop()
    if teacher_only and st.session_state.get("role") != "teacher":
        st.error("该页面仅限教师访问。")
        st.info("学生端不提供教师管理入口；如需帮助，请联系任课教师。")
        if st.button("返回首页"):
            st.switch_page("app.py")
        st.stop()


def render_shell(*, teacher_only: bool = False) -> None:
    require_login(teacher_only=teacher_only)
    identity = current_identity()
    sidebar_navigation(
        str(st.session_state.get("role", "student")),
        identity.public_label,
        session_code(identity.session_token),
    )


def student_page(title: str, *, overline: str = "DSP 学习空间") -> None:
    setup_page(title)
    render_shell()
