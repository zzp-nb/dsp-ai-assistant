"""Shared visual language for the DSP teaching platform."""

from __future__ import annotations

import html

import streamlit as st

PRIMARY = "#12355B"
ACCENT = "#2A9D8F"
WARM = "#D97757"
INK = "#172033"
MUTED = "#5D6B82"

FEATURES = [
    ("01", "智能问答", "基于课程资料回答 DSP 概念问题，支持通俗、专业、推导三种讲法。", "pages/1_智能问答.py", "qa"),
    ("02", "课程知识库", "查看 PPT/PDF 导入、解析与索引状态，检索章节依据。", "pages/2_课程知识库.py", "kb"),
    ("03", "公式推导", "从符号含义到分步推导、例子与常见错误，完整展示过程。", "pages/3_公式推导.py", "formula"),
    ("04", "智能习题", "按章节、题型、难度生成练习，答案与解析逐题对应。", "pages/4_智能习题.py", "quiz"),
    ("05", "信号仿真", "调参数观察采样、混叠、卷积、FFT、FIR 与 IIR 的真实结果。", "pages/5_信号仿真.py", "sim"),
    ("06", "课堂互动", "提交课堂问题，教师选择后投影展示，不自动公开。", "pages/6_课堂互动.py", "class"),
]

NAV_ITEMS = [
    ("首页", "app.py"),
    ("智能问答", "pages/1_智能问答.py"),
    ("课程知识库", "pages/2_课程知识库.py"),
    ("公式推导", "pages/3_公式推导.py"),
    ("智能习题", "pages/4_智能习题.py"),
    ("信号仿真", "pages/5_信号仿真.py"),
    ("课堂互动", "pages/6_课堂互动.py"),
    ("课堂大屏", "pages/8_课堂展示.py"),
]


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        :root {{
            --dsp-primary: {PRIMARY};
            --dsp-accent: {ACCENT};
            --dsp-warm: {WARM};
            --dsp-ink: {INK};
            --dsp-muted: {MUTED};
            --dsp-border: #DDE5EF;
            --dsp-surface: #FFFFFF;
            --dsp-bg: #F7F9FC;
        }}
        html, body, [class*="css"] {{
            font-family: "Inter", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif;
        }}
        .stApp {{ background: var(--dsp-bg); }}
        [data-testid="stHeader"] {{ background: rgba(247,249,252,0.86); backdrop-filter: blur(8px); }}
        [data-testid="stSidebar"] {{
            background: linear-gradient(180deg, #0D2947 0%, #12355B 55%, #173F66 100%);
            border-right: 1px solid rgba(255,255,255,0.08);
        }}
        [data-testid="stSidebar"] * {{ color: #F4F8FD; }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a {{
            border-radius: 10px; padding: 0.18rem 0.45rem; color: #DCE8F6 !important;
        }}
        [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover {{ background: rgba(255,255,255,0.10); }}
        [data-testid="stSidebar"] hr {{ border-color: rgba(255,255,255,0.12); }}
        [data-testid="stSidebar"] .stButton > button,
        [data-testid="stSidebar"] button[kind="secondary"] {{
            background: rgba(255,255,255,0.08) !important;
            color: #F4F8FD !important;
            border: 1px solid rgba(255,255,255,0.20) !important;
            box-shadow: none;
        }}
        [data-testid="stSidebar"] .stButton > button:hover,
        [data-testid="stSidebar"] button[kind="secondary"]:hover {{
            background: rgba(255,255,255,0.15) !important;
            color: #FFFFFF !important;
            border-color: rgba(255,255,255,0.32) !important;
        }}
        [data-testid="stSidebar"] button p {{ color: #F4F8FD !important; }}
        [data-testid="stSidebarNav"] {{ display: none; }}
        .block-container {{ max-width: 1240px; padding-top: 2.2rem; padding-bottom: 3rem; }}
        h1, h2, h3 {{ color: var(--dsp-ink); letter-spacing: -0.02em; }}
        h1 {{ font-weight: 760; }}
        a {{ color: var(--dsp-primary); }}

        .dsp-brand {{
            display:flex; align-items:center; gap:12px; padding: 0.35rem 0 0.9rem 0;
        }}
        .dsp-mark {{
            width: 42px; height: 42px; border-radius: 12px;
            background: linear-gradient(135deg, #2A9D8F 0%, #8ED6CB 100%);
            display:flex; align-items:center; justify-content:center;
            color:#062B33; font-weight:800; font-size:14px; letter-spacing:-0.04em;
            box-shadow: 0 8px 24px rgba(42,157,143,0.28);
        }}
        .dsp-brand-title {{ font-weight: 720; font-size: 1.02rem; line-height:1.15; color:#fff; }}
        .dsp-brand-sub {{ font-size:0.70rem; color:#A9C2DC; letter-spacing:0.08em; margin-top:3px; }}

        .dsp-hero {{
            position: relative; overflow: hidden;
            background: linear-gradient(120deg, #0D2947 0%, #12355B 52%, #1A466F 100%);
            color: #fff; border-radius: 24px; padding: 3.0rem 3.0rem 2.6rem 3.0rem;
            box-shadow: 0 24px 60px rgba(18,53,91,0.20);
            margin-bottom: 1.6rem;
        }}
        .dsp-hero:after {{
            content:""; position:absolute; right:-120px; top:-140px; width:430px; height:430px;
            border-radius:50%; border:1px solid rgba(142,214,203,0.25);
            box-shadow: 0 0 0 60px rgba(142,214,203,0.04), 0 0 0 130px rgba(142,214,203,0.025);
        }}
        .dsp-kicker {{
            display:inline-block; font-size:0.74rem; letter-spacing:0.18em; text-transform:uppercase;
            color:#9BE0D5; border:1px solid rgba(155,224,213,0.35); border-radius:999px;
            padding:0.28rem 0.7rem; margin-bottom:1.0rem;
        }}
        .dsp-hero h1 {{ color:#fff; font-size: clamp(2.1rem, 4vw, 3.6rem); line-height:1.08; margin:0 0 0.8rem 0; }}
        .dsp-hero p {{ color:#C9D9E9; max-width: 700px; font-size:1.02rem; line-height:1.75; margin:0; }}
        .dsp-hero-meta {{ display:flex; gap:1.6rem; flex-wrap:wrap; margin-top:1.8rem; color:#A9C2DC; font-size:0.82rem; }}
        .dsp-hero-meta strong {{ color:#fff; font-weight:650; }}

        .dsp-page-head {{ padding: 0.25rem 0 0.9rem 0; border-bottom:1px solid var(--dsp-border); margin-bottom:1.4rem; }}
        .dsp-page-head .dsp-overline {{
            color: var(--dsp-accent); font-size:0.74rem; letter-spacing:0.13em; font-weight:700; text-transform:uppercase;
        }}
        .dsp-page-head h1 {{ font-size: clamp(1.65rem, 2.6vw, 2.2rem); margin:0.32rem 0 0.35rem 0; }}
        .dsp-page-head p {{ color: var(--dsp-muted); margin:0; line-height:1.65; max-width:820px; }}

        .dsp-card {{
            background:var(--dsp-surface); border:1px solid var(--dsp-border); border-radius:18px;
            padding:1.35rem 1.35rem 1.15rem 1.35rem; height:100%;
            box-shadow: 0 8px 24px rgba(18,53,91,0.045);
            transition: transform .15s ease, box-shadow .15s ease;
        }}
        .dsp-card:hover {{ transform: translateY(-2px); box-shadow: 0 14px 32px rgba(18,53,91,0.09); }}
        .dsp-card-icon {{
            width:40px; height:40px; border-radius:10px; background:#E8F3F5; color:#176B64;
            display:flex; align-items:center; justify-content:center; font-weight:760; font-size:0.82rem;
            letter-spacing:0.02em; margin-bottom:0.9rem;
        }}
        .dsp-card h3 {{ font-size:1.08rem; margin:0 0 0.42rem 0; }}
        .dsp-card p {{ color:var(--dsp-muted); font-size:0.88rem; line-height:1.65; margin:0 0 0.75rem 0; min-height:3.4rem; }}
        .dsp-card .dsp-card-link {{ color:var(--dsp-primary); font-size:0.86rem; font-weight:650; }}

        .dsp-panel {{
            background:var(--dsp-surface); border:1px solid var(--dsp-border); border-radius:16px;
            padding:1.25rem 1.35rem; box-shadow:0 6px 20px rgba(18,53,91,0.04);
        }}
        .dsp-note {{
            border-left:3px solid var(--dsp-accent); background:#F0F8F7; border-radius:0 10px 10px 0;
            padding:0.8rem 1rem; color:#245A56; font-size:0.88rem; line-height:1.65;
        }}
        .dsp-warn {{ border-left-color:#D97757; background:#FDF4F0; color:#7A402B; }}
        .dsp-source {{
            border:1px solid var(--dsp-border); border-radius:12px; padding:0.8rem 0.95rem;
            background:#FBFCFE; margin-bottom:0.55rem;
        }}
        .dsp-source-top {{ display:flex; justify-content:space-between; gap:1rem; font-size:0.82rem; }}
        .dsp-source-name {{ font-weight:650; color:var(--dsp-primary); }}
        .dsp-source-loc {{ color:var(--dsp-muted); white-space:nowrap; }}
        .dsp-source-snippet {{ color:#4E5D75; font-size:0.82rem; line-height:1.6; margin-top:0.35rem; }}
        .dsp-badge {{
            display:inline-block; border-radius:999px; padding:0.18rem 0.6rem; font-size:0.72rem;
            font-weight:650; background:#E8F3F5; color:#176B64; margin-right:0.35rem;
        }}
        .dsp-badge-muted {{ background:#EEF2F7; color:#58677D; }}
        .dsp-badge-warm {{ background:#FDF0EA; color:#9A4A2F; }}
        .dsp-question {{
            font-size:clamp(1.3rem, 2.4vw, 2.0rem); line-height:1.55; font-weight:650; color:var(--dsp-ink);
        }}
        .dsp-display-wrap {{
            background:#fff; border:1px solid var(--dsp-border); border-radius:24px;
            padding:2.3rem 3rem; min-height:260px; box-shadow: 0 20px 60px rgba(18,53,91,0.10);
        }}
        .dsp-stat-row {{ display:flex; gap:0.9rem; flex-wrap:wrap; }}
        .dsp-stat {{
            flex:1 1 150px; background:#fff; border:1px solid var(--dsp-border); border-radius:14px; padding:1rem 1.1rem;
        }}
        .dsp-stat .n {{ font-size:1.7rem; font-weight:760; color:var(--dsp-primary); line-height:1.1; }}
        .dsp-stat .l {{ color:var(--dsp-muted); font-size:0.78rem; margin-top:0.35rem; }}

        div[data-testid="stForm"] {{ border:1px solid var(--dsp-border); border-radius:16px; padding:1rem 1.1rem; background:#fff; }}
        .stButton > button, .stDownloadButton > button {{
            border-radius:10px; font-weight:600; border:1px solid #C9D6E5;
        }}
        .stButton > button[kind="primary"] {{ background:var(--dsp-primary); border-color:var(--dsp-primary); }}
        .stButton > button[kind="primary"]:hover {{ background:#0D2947; border-color:#0D2947; }}
        .stChatMessage {{ background:transparent; }}
        div[data-testid="stExpander"] {{ border:1px solid var(--dsp-border); border-radius:12px; background:#fff; }}
        .katex-display {{ overflow-x:auto; overflow-y:hidden; padding:0.35rem 0; }}
        footer {{ visibility:hidden; }}
        #MainMenu {{ visibility:hidden; }}
        @media (max-width: 760px) {{
            .block-container {{ padding:1.1rem 0.9rem 2rem 0.9rem; }}
            .dsp-hero {{ padding:2rem 1.3rem 1.8rem 1.3rem; border-radius:18px; }}
            .dsp-hero h1 {{ font-size:2.1rem; }}
            .dsp-display-wrap {{ padding:1.4rem; }}
            .dsp-card p {{ min-height:auto; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_brand(sidebar: bool = False) -> None:
    markup = """
    <div class="dsp-brand">
      <div class="dsp-mark">DSP</div>
      <div>
        <div class="dsp-brand-title">DSP AI 智能教学助手</div>
        <div class="dsp-brand-sub">DIGITAL SIGNAL PROCESSING</div>
      </div>
    </div>
    """
    if sidebar:
        st.sidebar.markdown(markup, unsafe_allow_html=True)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def page_header(overline: str, title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="dsp-page-head">
          <div class="dsp-overline">{html.escape(overline)}</div>
          <h1>{html.escape(title)}</h1>
          <p>{html.escape(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hero() -> None:
    st.markdown(
        """
        <section class="dsp-hero">
          <div class="dsp-kicker">大学课程 · 教学与自主学习</div>
          <h1>DSP AI 智能教学助手</h1>
          <p>数字信号处理课程智能学习与教学平台。用课程资料为依据，把抽象的信号、频谱与滤波器，
          变成可以追问、推导、练习和亲手调节的课堂体验。</p>
          <div class="dsp-hero-meta">
            <span><strong>6</strong> 个学习模块</span>
            <span><strong>RAG</strong> 课程资料检索</span>
            <span><strong>DeepSeek</strong> 服务端调用</span>
            <span><strong>免注册</strong> 班级密码进入</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def feature_grid() -> None:
    columns = st.columns(3, gap="medium")
    for index, (number, title, description, page, _key) in enumerate(FEATURES):
        with columns[index % 3]:
            st.markdown(
                f"""
                <div class="dsp-card">
                  <div class="dsp-card-icon">{number}</div>
                  <h3>{html.escape(title)}</h3>
                  <p>{html.escape(description)}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.page_link(page, label=f"进入{title} →", icon=None)
            st.write("")


def stat_row(items: list[tuple[str, str]]) -> None:
    cells = "".join(
        f'<div class="dsp-stat"><div class="n">{html.escape(str(value))}</div>'
        f'<div class="l">{html.escape(label)}</div></div>'
        for value, label in items
    )
    st.markdown(f'<div class="dsp-stat-row">{cells}</div>', unsafe_allow_html=True)


def note(text: str, *, warning: bool = False) -> None:
    klass = "dsp-note dsp-warn" if warning else "dsp-note"
    st.markdown(f'<div class="{klass}">{html.escape(text)}</div>', unsafe_allow_html=True)


def sidebar_navigation(role: str, display_name: str, session_code: str) -> None:
    with st.sidebar:
        render_brand(sidebar=True)
        st.caption("课程导航")
        for label, page in NAV_ITEMS:
            st.page_link(page, label=label)
        if role == "teacher":
            st.page_link("pages/7_教师管理.py", label="教师管理")
        st.divider()
        role_label = "教师" if role == "teacher" else "学生"
        st.markdown(
            f'<div style="font-size:0.78rem;color:#A9C2DC">当前身份</div>'
            f'<div style="font-weight:650;margin:0.2rem 0 0.1rem 0">{html.escape(role_label)} · '
            f'{html.escape(display_name)}</div>'
            f'<div style="font-size:0.7rem;color:#8FAAC5">会话 {html.escape(session_code)}</div>',
            unsafe_allow_html=True,
        )
        if st.button("退出登录", width="stretch", key="sidebar_logout"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.switch_page("app.py")


def footer() -> None:
    st.markdown(
        """
        <div style="margin-top:2.8rem;padding-top:1.1rem;border-top:1px solid #DDE5EF;
                    color:#8493A8;font-size:0.76rem;line-height:1.7">
          DSP AI 智能教学助手 · 回答仅供课程学习参考，重要结论请以教师讲解和教材为准。<br>
          课程资料不会上传到公开仓库；AI 调用在服务端完成。
        </div>
        """,
        unsafe_allow_html=True,
    )
