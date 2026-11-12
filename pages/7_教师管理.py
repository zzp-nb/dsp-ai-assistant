"""Teacher administration: classroom questions, projection, usage, limits and API."""

from __future__ import annotations

import html

import streamlit as st

from core.ai_service import friendly_error
from core.cost_tracker import format_cny
from core.database import local_day_bounds_utc
from core.limits import get_runtime_limits
from core.rag_engine import manifest_for_ui
from ui.content import format_local_time, render_citations
from ui.guard import render_shell, setup_page
from ui.runtime import current_identity, services
from ui.theme import footer, note, page_header, stat_row


setup_page("教师管理")
render_shell(teacher_only=True)
page_header(
    "TEACHER CONSOLE",
    "教师管理",
    "查看课堂问题并自主决定是否投影；掌握 API 调用、费用与全班额度。这里不会自动把学生问题推上大屏。",
)

ctx = services()
config, db, rag, ai = ctx.config, ctx.db, ctx.rag, ctx.ai
identity = current_identity()
limits = get_runtime_limits(db, config)
flash = st.session_state.pop("teacher_flash", None)
if flash:
    st.success(flash)
if config.use_offline:
    note(
        f"当前为完全离线模式：{ai.offline.entry_count} 个内置 DSP 知识主题，"
        "问答、推导、习题均不调用 API；学生不消耗 API 额度。"
    )

tab_questions, tab_stats, tab_settings, tab_system = st.tabs(
    ["课堂问题", "使用统计与费用", "调用额度设置", "API 与系统"]
)

with tab_questions:
    current = db.get_displayed_question()
    st.markdown("#### 当前大屏")
    if current:
        st.success(f"正在展示问题 #{current['id']} · {format_local_time(current['created_at'])}")
        st.markdown(f"**{current['question']}**")
        if current["ai_answer"]:
            with st.expander("当前 AI 回答", expanded=False):
                st.markdown(current["ai_answer"])
            answer_visible = st.toggle(
                "在大屏展示 AI 回答",
                value=current["show_ai_answer"],
                key="current_show_answer",
            )
            action_cols = st.columns(2)
            with action_cols[0]:
                if st.button("更新大屏显示", type="primary"):
                    db.set_question_show_answer(current["id"], answer_visible)
                    st.rerun()
            with action_cols[1]:
                if st.button("关闭课堂展示"):
                    db.set_question_display(None)
                    st.rerun()
        else:
            st.info("这个问题还没有 AI 回答，大屏只展示问题。")
            if st.button("关闭课堂展示", key="close_current_no_answer"):
                db.set_question_display(None)
                st.rerun()
        st.page_link("pages/8_课堂展示.py", label="打开课堂投影大屏 →")
    else:
        st.info("当前没有展示中的问题。学生在课堂互动页提交的问题不会自动上屏。")
        st.page_link("pages/8_课堂展示.py", label="打开课堂投影大屏 →")

    st.divider()
    header_col, filter_col = st.columns([2.4, 1])
    with header_col:
        st.markdown("#### 学生问题列表")
    with filter_col:
        status_filter = st.selectbox(
            "筛选", ["全部", "待处理", "已生成回答", "展示中"], label_visibility="collapsed"
        )
    all_questions = db.list_classroom_questions(limit=200)
    if status_filter == "待处理":
        questions = [item for item in all_questions if item["status"] == "pending"]
    elif status_filter == "已生成回答":
        questions = [item for item in all_questions if item["status"] == "answered" and not item["is_displayed"]]
    elif status_filter == "展示中":
        questions = [item for item in all_questions if item["is_displayed"]]
    else:
        questions = all_questions

    if not questions:
        st.caption("暂无符合条件的问题。")
    for item in questions:
        with st.container(border=True):
            head = st.columns([3.4, 1.2, 1.0])
            with head[0]:
                st.markdown(
                    f'<span class="dsp-badge {"" if item["is_displayed"] else "dsp-badge-muted"}">'
                    f'#{item["id"]} {"展示中" if item["is_displayed"] else "课堂问题"}</span>'
                    f'<span style="font-weight:650;margin-left:0.35rem">{html.escape(item["student_name"])}</span>'
                    f'<span style="color:#8493A8;font-size:0.78rem;margin-left:0.5rem">'
                    f'{format_local_time(item["created_at"])}</span>',
                    unsafe_allow_html=True,
                )
            with head[1]:
                label = {"pending": "待处理", "answered": "已生成回答", "archived": "已归档"}.get(
                    item["status"], item["status"]
                )
                st.caption(label)
            with head[2]:
                st.caption(f"#{item['id']}")
            st.markdown(item["question"])
            if item["ai_answer"]:
                with st.expander("查看 / 隐藏 AI 回答", expanded=item["is_displayed"]):
                    st.markdown(item["ai_answer"])
                    render_citations(item["ai_citations"])
            show_answer = st.checkbox(
                "若展示，包含 AI 回答",
                value=bool(item["show_ai_answer"]),
                key=f"show_answer_{item['id']}",
                disabled=not bool(item["ai_answer"]),
            )
            actions = st.columns(4)
            with actions[0]:
                generate_label = "重新生成 AI 回答" if item["ai_answer"] else "生成 AI 回答"
                if st.button(generate_label, key=f"generate_{item['id']}", type="primary", width="stretch"):
                    if not config.api_configured:
                        st.error("尚未配置 DeepSeek API Key，无法生成回答。")
                    else:
                        with st.spinner("正在检索课程资料并生成课堂回答…"):
                            try:
                                result = ai.answer_classroom_question(
                                    item["question"], identity.session_token
                                )
                            except Exception as exc:
                                st.error(friendly_error(exc))
                            else:
                                db.save_question_answer(
                                    item["id"],
                                    answer=result.content,
                                    citations=result.citations,
                                    show_answer=show_answer,
                                )
                                st.rerun()
            with actions[1]:
                if st.button("仅展示问题", key=f"display_q_{item['id']}", width="stretch"):
                    db.set_question_display(item["id"], show_ai_answer=False)
                    st.rerun()
            with actions[2]:
                if st.button(
                    "展示问题 + AI",
                    key=f"display_a_{item['id']}",
                    width="stretch",
                    disabled=not bool(item["ai_answer"]),
                ):
                    db.set_question_display(item["id"], show_ai_answer=True)
                    st.rerun()
            with actions[3]:
                if item["is_displayed"]:
                    if st.button("关闭展示", key=f"close_{item['id']}", width="stretch"):
                        db.set_question_display(None)
                        st.rerun()
                else:
                    st.caption("未展示")
        st.write("")

with tab_stats:
    start_today, end_today = local_day_bounds_utc()
    summary = db.usage_summary(start_today, end_today)
    active = db.active_learners_today()
    calls = int(summary.get("calls") or 0)
    tokens = int(summary.get("total_tokens") or 0)
    cost = float(summary.get("cost_cny") or 0)
    stat_row(
        [
            (str(calls), "今日 AI 调用"),
            (str(active), "今日活跃会话"),
            (f"{tokens:,}", "今日 Token"),
            (format_cny(cost), "今日估算费用"),
        ]
    )
    st.caption(
        f"今日剩余全班额度：{max(0, limits.daily_global_limit - db.count_calls_since(start_today))} / "
        f"{limits.daily_global_limit} 次。价格版本：{config.pricing.get('version', '未配置')}；"
        "费用为按 token 的估算值，实际以 DeepSeek 账单为准。"
        + (" 当前为离线模式，以下 API 统计应保持为 0。" if config.use_offline else "")
    )
    st.write("")

    feature_labels = {
        "qa": "智能问答",
        "formula": "公式推导",
        "quiz": "智能习题",
        "classroom": "课堂回答",
        "connection_test": "连接测试",
    }
    feature_rows = db.usage_by_feature(start_today)
    if feature_rows:
        st.markdown("#### 今日功能用量")
        rows = [
            {
                "功能": feature_labels.get(row["feature"], row["feature"]),
                "调用次数": row["calls"],
                "Token": row["total_tokens"],
                "估算费用": format_cny(float(row["cost_cny"] or 0)),
            }
            for row in feature_rows
        ]
        st.dataframe(rows, width="stretch", hide_index=True)
    else:
        st.info("今天还没有 AI 调用记录。")

    st.markdown("#### 最近调用")
    recent = db.recent_calls(limit=50)
    if recent:
        rows = []
        for row in recent:
            rows.append(
                {
                    "时间": format_local_time(row["created_at"]),
                    "功能": feature_labels.get(row["feature"], row["feature"]),
                    "模型": row["model"],
                    "Token": row["total_tokens"],
                    "费用": format_cny(float(row["cost_cny"] or 0)),
                    "结果": "成功" if row["status"] == "success" else ("等待" if row["status"] == "pending" else "失败"),
                    "错误": row["error_code"] or "",
                    "延迟(ms)": row["latency_ms"] or "",
                }
            )
        st.dataframe(rows, width="stretch", hide_index=True)
        st.caption("不展示学生原始对话内容；学生对话按会话隔离。教师只在此查看课堂问题与汇总指标。")
    else:
        st.caption("暂无调用记录。")

    with st.expander("按学生标识查看调用量"):
        student_rows = db.usage_by_student(start_today)
        if student_rows:
            display_rows = [
                {
                    "学生标识（哈希）": row["student_key"][:12] if row["student_key"] else "教师",
                    "调用次数": row["calls"],
                    "Token": row["total_tokens"],
                    "估算费用": format_cny(float(row["cost_cny"] or 0)),
                }
                for row in student_rows
            ]
            st.dataframe(display_rows, width="stretch", hide_index=True)
            st.caption("无账号模式下使用哈希标识，避免在统计表中存明文身份。")
        else:
            st.caption("暂无数据。")

with tab_settings:
    st.markdown("#### 每日额度与输入输出限制")
    st.caption("修改后立即生效。额度按上海时区每日 00:00 重置；教师课堂回答不计学生个人额度，但仍计入全班总量。")
    with st.form("limits_form", border=True):
        col1, col2 = st.columns(2)
        with col1:
            student_limit = st.number_input(
                "每位学生每日调用上限（次）",
                min_value=1,
                max_value=200,
                value=limits.daily_student_limit,
                step=1,
            )
            max_input = st.number_input(
                "单次输入字符上限",
                min_value=100,
                max_value=3000,
                value=limits.max_input_chars,
                step=100,
            )
        with col2:
            global_limit = st.number_input(
                "全班每日调用总量上限（次）",
                min_value=1,
                max_value=5000,
                value=limits.daily_global_limit,
                step=10,
            )
            max_output = st.number_input(
                "单次输出 Token 上限",
                min_value=100,
                max_value=4000,
                value=limits.max_output_tokens,
                step=100,
            )
        save_limits = st.form_submit_button("保存设置", type="primary")
    if save_limits:
        if global_limit < student_limit:
            st.warning("全班总量小于单个学生额度，可能导致课堂开始后很快耗尽。建议全班总量至少为单人的 10 倍。")
        db.set_settings(
            {
                "daily_student_limit": int(student_limit),
                "daily_global_limit": int(global_limit),
                "max_input_chars": int(max_input),
                "max_output_tokens": int(max_output),
            }
        )
        st.session_state["teacher_flash"] = "设置已保存。"
        st.rerun()

    st.divider()
    st.markdown("#### 费用配置说明")
    pricing_models = config.pricing_models
    st.markdown(
        f"当前价格版本：**{config.pricing.get('version', '未配置')}**。"
        "估算价格来自 `config/pricing.json`，不会写死在业务代码里。"
    )
    if pricing_models:
        rows = []
        for model, values in pricing_models.items():
            rows.append(
                {
                    "模型": model,
                    "缓存命中输入（元/百万 token）": values.get("input_cache_hit_cny_per_million", "—"),
                    "缓存未命中输入（元/百万 token）": values.get("input_cache_miss_cny_per_million", "—"),
                    "输出（元/百万 token）": values.get("output_cny_per_million", "—"),
                }
            )
        st.dataframe(rows, width="stretch", hide_index=True)
    st.caption(
        "DeepSeek 调整价格后，请修改服务器上的 config/pricing.json 并重启应用；"
        "不要依赖本页显示的估算值作为财务凭据。"
    )
    note(
        "无账号模式下，学生换浏览器/清空会话可能重新获得一个新会话额度；"
        "因此个人额度不是强安全边界。请同时设置全班每日总量，并在课堂上说明使用规范。",
        warning=True,
    )

with tab_system:
    st.markdown("#### 运行模式与 DeepSeek")
    status_cols = st.columns(3)
    if config.use_offline:
        status_cols[0].metric("运行模式", "本地离线")
        status_cols[1].metric("内置知识", f"{ai.offline.entry_count} 个主题")
        status_cols[2].metric("API 调用", "不调用")
        st.info(
            "当前完全离线：不需要网络，也不需要 DeepSeek Key。"
            "问答、推导和习题全部使用内置知识库；不会产生 API 费用。"
        )
        st.caption(
            "如需切换在线模式，将 .env 或 Streamlit Secrets 中的 "
            "`DSP_OFFLINE_MODE` 改为 false，并配置有效的 `DEEPSEEK_API_KEY`，然后重启应用。"
        )
    else:
        status_cols[0].metric("API Key", "已配置" if config.api_configured else "未配置")
        status_cols[1].metric("对话模型", config.deepseek_model)
        status_cols[2].metric("请求超时", f"{config.request_timeout_seconds}s")
        st.caption(f"服务端地址：{config.deepseek_base_url} · 密钥不会发送到浏览器。")
        if st.button("测试 DeepSeek 连接", type="primary"):
            if not config.api_configured:
                st.error("尚未配置 DEEPSEEK_API_KEY。")
            else:
                with st.spinner("正在发起一次最小测试请求…"):
                    try:
                        result = ai.test_connection(identity.session_token)
                    except Exception as exc:
                        st.error(friendly_error(exc))
                    else:
                        st.success(f"连接成功：{result.content[:80]}")
                        st.caption(
                            f"延迟 {result.latency_ms} ms · 本次约 {result.usage.get('total_tokens', 0)} tokens · "
                            f"估算费用 {format_cny(result.cost_cny)}"
                        )
    st.divider()
    st.markdown("#### 课程资料与索引")
    index_meta = manifest_for_ui(config.vector_dir)
    materials = db.list_materials()
    stat_row(
        [
            (str(len(materials)), "资料记录"),
            (str(index_meta.get("chunk_count", 0)), "文本块"),
            (index_meta.get("created_at", "尚未建立")[:16].replace("T", " "), "索引创建时间"),
        ]
    )
    st.page_link("pages/2_课程知识库.py", label="管理课程资料与索引 →")
    st.divider()
    st.markdown("#### 存储与安全")
    st.markdown(
        f"- 数据库：`{config.db_path}`\n"
        f"- 课程资料：`{config.materials_dir}`\n"
        f"- 索引目录：`{config.vector_dir}`\n"
        "- DeepSeek Key、班级密码、教师密码只从服务端环境变量/Streamlit Secrets 读取。"
    )
    st.warning(
        "Streamlit Community Cloud 的文件系统不保证持久化。休眠或重新部署后，SQLite 数据、"
        "上传资料和索引可能丢失。正式长期使用请挂载持久磁盘，或按 README 的替代存储方案部署。"
    )
    st.markdown("#### 部署检查")
    st.markdown(
        "- [ ] `.env` / Streamlit Secrets 已配置三个密钥\n"
        "- [ ] 修改了默认班级密码和教师密码\n"
        "- [ ] 课程资料未提交到公开 GitHub\n"
        "- [ ] 已在教师端测试 DeepSeek 连接\n"
        "- [ ] 已设置学生与全班每日额度\n"
        "- [ ] 已建立知识库索引并抽查引用页码"
    )

footer()
