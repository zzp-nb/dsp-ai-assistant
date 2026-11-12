"""DSP AI 智能教学助手 — landing page, role selection and password gates."""

from __future__ import annotations

import streamlit as st

from core.auth import verify_password
from knowledge import ENTRIES
from ui.guard import render_shell, setup_page
from ui.runtime import (
    bootstrap,
    establish_session,
    record_login_failure,
    reset_login_failures,
    throttle_login,
)
from ui.theme import feature_grid, footer, hero, note, stat_row


setup_page("首页")
config, db = bootstrap()

if not st.session_state.get("authenticated"):
    with st.sidebar:
        st.markdown(
            """
            <div style="padding:0.5rem 0 1rem 0">
              <div style="font-size:1.0rem;font-weight:700;color:#fff">DSP AI 智能教学助手</div>
              <div style="font-size:0.72rem;letter-spacing:0.08em;color:#9BB6D1;margin-top:4px">
                DIGITAL SIGNAL PROCESSING
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption("班级密码进入 · 无需注册")
        if config.use_offline:
            st.caption("完全离线运行：不联网、不调用 API、无 Token 费用。")
        else:
            st.caption("AI 由服务端统一调用，密钥不会出现在浏览器。")
        st.divider()
        st.caption("教师请使用独立教师密码进入管理界面。")
    hero()
    if config.use_offline:
        note("当前为完全离线模式：问答、公式推导和习题使用内置 DSP 知识库，断网也能使用。")
    if config.setup_issues:
        st.warning("部署配置尚未完成：" + "；".join(config.setup_issues) + "。请按 README 配置服务端环境变量或 Secrets。")
    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        st.markdown("### 一个面向课堂与课后的 DSP 学习空间")
        st.markdown(
            """
            这里不是通用聊天窗口。回答优先检索教师 PPT 和教材，标注资料与页码；
            你可以切换通俗、专业、推导三种讲法，也可以直接调参数做信号仿真。

            - **课程依据**：RAG 检索 PPT / 教材，找不到就明确说明
            - **连续追问**：围绕一个概念逐步深入
            - **公式与习题**：分步推导、题目与解析逐题对应
            - **课堂互动**：问题先进入教师面板，由教师决定是否投影
            """
        )
        st.markdown(
            '<div class="dsp-note">学生端不需要注册，也不会上传你的个人账号信息。'
            "学号/昵称仅用于课堂问题标识与每日额度，可留空。</div>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown("#### 进入课程")
        role = st.radio(
            "选择入口",
            ["学生入口", "教师入口"],
            horizontal=True,
            label_visibility="collapsed",
        )
        allowed, lock_message = throttle_login()
        if not allowed:
            st.error(lock_message)
        if role == "学生入口":
            with st.form("student_login", border=True):
                student_no = st.text_input(
                    "学号 / 昵称（选填）",
                    max_chars=24,
                    placeholder="例如：2026张三",
                    help="仅用于课堂问题标识和今日额度，不做账号注册。留空则使用本次浏览器会话。",
                )
                password = st.text_input("班级访问密码", type="password")
                submitted = st.form_submit_button("进入学习空间", type="primary", width="stretch")
            if submitted and allowed:
                if not config.class_password:
                    st.error("教师尚未配置班级访问密码，请联系任课教师。")
                elif verify_password(password, config.class_password):
                    try:
                        establish_session("student", student_no, display_name=student_no)
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        reset_login_failures()
                        st.rerun()
                else:
                    record_login_failure()
                    st.error("班级访问密码不正确。请检查后重试，或联系任课教师。")
            st.caption("忘记密码请直接询问任课教师，系统不会向学生展示密码。")
        else:
            with st.form("teacher_login", border=True):
                password = st.text_input("教师管理密码", type="password")
                submitted = st.form_submit_button("进入教师管理", type="primary", width="stretch")
            if submitted and allowed:
                if not config.teacher_password:
                    st.error("尚未配置教师密码，请先完成服务端配置。")
                elif verify_password(password, config.teacher_password):
                    establish_session("teacher", "", display_name="教师")
                    reset_login_failures()
                    st.rerun()
                else:
                    record_login_failure()
                    st.error("教师密码不正确。")
            if config.use_offline:
                st.caption("当前为本地离线模式，教师端可管理课堂问题、资料和投影。")
            else:
                st.caption("教师入口可查看课堂问题、调用量与额度，并可测试 API 连接。")
    footer()
    st.stop()

render_shell()
identity = st.session_state.get("display_name") or "同学"
hero()
st.markdown(f"### 你好，{identity}")
st.caption("选择一个模块开始，或先到课堂互动提交问题。")
if config.use_offline:
    note(
        "当前离线：问答、推导、习题全部来自本地知识库，断网可用、无 API 费用。"
        "上传的 PPT/PDF 仍可本地解析。"
    )

materials = db.list_materials()
ready_materials = sum(1 for material in materials if material.get("status") == "ready")
stat_row(
    [
        (str(len(materials)), "已导入课程资料"),
        (str(ready_materials), "索引可用资料"),
        (str(len(ENTRIES)), "内置知识主题"),
        ("本地离线" if config.use_offline else "DeepSeek 在线", "回答引擎"),
    ]
)
st.write("")
feature_grid()

if st.session_state.get("role") == "teacher":
    st.write("")
    st.markdown("---")
    st.markdown("#### 教师工作台")
    teacher_cols = st.columns(3)
    with teacher_cols[0]:
        st.page_link("pages/7_教师管理.py", label="课堂问题与用量管理")
    with teacher_cols[1]:
        st.page_link("pages/2_课程知识库.py", label="导入与重建课程知识库")
    with teacher_cols[2]:
        st.page_link("pages/8_课堂展示.py", label="打开课堂投影大屏")
else:
    st.write("")
    note(
        "课堂问题不会自动出现在大屏上。提交后由教师选择并点击“展示到课堂”，"
        "你可以在课堂互动页查看处理状态。"
    )

footer()
