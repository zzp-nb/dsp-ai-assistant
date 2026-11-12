"""Course knowledge base: material status, import, indexing and retrieval preview."""

from __future__ import annotations

import streamlit as st

from core.document_loader import SUPPORTED_EXTENSIONS
from core.rag_engine import build_index, invalidate_rag_engine, manifest_for_ui
from core.storage import StorageError, get_material_storage
from ui.content import format_local_time, render_citations
from ui.guard import render_shell, setup_page
from ui.runtime import current_identity, services
from ui.theme import footer, note, page_header, stat_row


setup_page("课程知识库")
render_shell()
page_header(
    "COURSE KNOWLEDGE BASE",
    "课程知识库",
    "把教师 PPT 与教材变成可检索、可引用的课程依据。第一版只解析可提取文字，图片与扫描页不伪装成已识别。",
)

ctx = services()
config, db, rag, ai = ctx.config, ctx.db, ctx.rag, ctx.ai
identity = current_identity()
is_teacher = identity.role == "teacher"
manifest = manifest_for_ui(config.vector_dir)
materials = db.list_materials()
storage = get_material_storage(config.materials_dir, max_size_mb=config.max_upload_mb)
files_on_disk = storage.list_files()
indexed_names = {item["source_name"] for item in materials}
pending_files = [path.name for path in files_on_disk if path.name not in indexed_names]
ready_count = sum(1 for item in materials if item["status"] == "ready")

stat_row(
    [
        (str(len(materials)), "课程资料"),
        (str(ready_count), "已索引资料"),
        (str(manifest.get("chunk_count", 0)), "课程文本块"),
        (str(ai.offline.entry_count), "内置知识主题"),
    ]
)
st.write("")

if config.use_offline:
    note(
        "当前为完全离线模式：内置 DSP 知识库可直接使用，不上传资料也能问答、推导和出题。"
        "上传的 PPT/PDF 仍会在本机解析并作为补充引用。"
    )

flash = st.session_state.pop("kb_flash", None)
if flash:
    st.success(flash.get("message", "操作完成。"))
    for warning in flash.get("warnings", []):
        st.warning(warning)
    for error in flash.get("errors", []):
        st.error(error)
if pending_files:
    st.warning("以下文件尚未建立索引：" + "、".join(pending_files))

if is_teacher:
    with st.expander("导入课程资料与重建索引", expanded=not materials):
        st.markdown("**上传 PPT / PDF / 补录文本**")
        st.caption(
            f"支持 {', '.join(sorted(SUPPORTED_EXTENSIONS))}；单文件不超过 {config.max_upload_mb} MB。"
            "文件保存在服务端数据目录，不会进入公开 GitHub。"
        )
        uploaded = st.file_uploader(
            "选择课程资料",
            type=["pdf", "pptx", "txt", "md"],
            accept_multiple_files=True,
            key="kb_uploader",
        )
        overwrite = st.checkbox("同名文件直接覆盖", value=False)
        if uploaded and st.button("保存上传文件", type="primary"):
            saved = 0
            for item in uploaded:
                try:
                    storage.save(item.name, bytes(item.getbuffer()), overwrite=overwrite)
                except StorageError as exc:
                    st.error(f"{item.name}：{exc}")
                else:
                    saved += 1
            if saved:
                st.session_state["kb_flash"] = {
                    "message": f"已保存 {saved} 个文件。请点击下方“重建课程索引”。"
                }
                st.rerun()

        st.divider()
        st.markdown("**重建检索索引**")
        st.caption("会重新解析目录内全部资料。首次部署或资料更新后执行一次即可；资料多时可能需要几十秒。")
        if st.button("重建课程索引", type="primary"):
            with st.spinner("正在解析 PDF/PPT 并建立混合检索索引…"):
                report = build_index(config.materials_dir, config.vector_dir, db)
                invalidate_rag_engine()
            if report.chunk_count:
                message = f"索引完成：{report.material_count} 份资料，{report.chunk_count} 个文本块。"
            else:
                message = "索引完成，但没有提取到可用文字。请检查资料是否为扫描件/图片。"
            st.session_state["kb_flash"] = {
                "message": message,
                "warnings": report.warnings,
                "errors": report.errors,
            }
            st.rerun()

    with st.expander("图片 / 扫描页文字补录（可选）"):
        st.markdown(
            """
            `python-pptx` 和 PyMuPDF 只能提取文本层，无法识别截图、公式图片或扫描 PDF。
            如需补录，请上传一个 UTF-8 文本文件，并按以下格式标记页码或幻灯片号：

            ```text
            [[PAGE 12]]
            这里是第 12 页扫描内容的人工转录。
            [[SLIDE 7]]
            这里是第 7 张幻灯片的图片文字。
            ```

            补录文件会保存为 `原文件名.pdf.ocr.txt` 或 `原文件名.pptx.ocr.txt`，
            然后重新建立索引。系统会标注该资料使用过补录文本。
            """
        )
        source_options = [item["source_name"] for item in materials if item["status"] in {"ready", "empty"}]
        if source_options:
            source_name = st.selectbox("对应资料", source_options)
            ocr_file = st.file_uploader("补录文本（.txt）", type=["txt"], key="ocr_uploader")
            if ocr_file is not None and st.button("保存补录文本"):
                try:
                    storage.write_sidecar(
                        source_name,
                        ocr_file.getvalue().decode("utf-8", errors="replace"),
                    )
                except StorageError as exc:
                    st.error(str(exc))
                else:
                    st.success("补录文本已保存。请重建索引使其生效。")
        else:
            st.caption("先导入并建立索引后，才能为具体资料补录文本。")

st.markdown("### 已导入资料")
if not materials:
    st.info("还没有资料记录。教师上传 PPT/PDF 后，点击“重建课程索引”。")
else:
    rows = []
    for item in materials:
        size_bytes = int(item["size_bytes"] or 0)
        size_label = f"{size_bytes} B" if size_bytes < 1024 else f"{size_bytes / 1024:.0f} KB"
        rows.append(
            {
                "资料名称": item["source_name"],
                "类型": {"pptx": "PPT", "pdf": "PDF", "text": "补充文本"}.get(item["doc_type"], item["doc_type"]),
                "状态": {"ready": "已索引", "empty": "无文本", "error": "解析失败", "pending": "待处理"}.get(
                    item["status"], item["status"]
                ),
                "页数/幻灯片": item["page_count"],
                "文本块": item["chunk_count"],
                "图片页": item["image_page_count"],
                "OCR补录": "是" if item["ocr_used"] else "否",
                "大小": size_label,
                "索引时间": format_local_time(item["indexed_at"]),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)

    errors = [item for item in materials if item["status"] == "error"]
    if errors:
        with st.expander("查看解析失败原因"):
            for item in errors:
                st.error(f"{item['source_name']}：{item['error'] or '未知错误'}")
    if any(item["image_page_count"] for item in materials):
        note(
            "部分资料包含只能作为图片读取的页面，系统没有假装完成 OCR。"
            "这些页面不会进入检索，除非教师通过上方补录文本入口提供内容。",
            warning=True,
        )
    if is_teacher:
        st.caption("如需删除资料，请从服务器 data/course_materials/ 目录移除文件后重建索引；不会从浏览器直接删除原始文件。")

if pending_files and is_teacher:
    st.caption("提示：上面列出的文件尚未建立索引。")

st.markdown("### 内置 DSP 知识库（离线可用）")
st.caption(
    f"共 {ai.offline.entry_count} 个主题，覆盖信号与系统、采样、Z 变换、DFT/FFT、"
    "滤波器、多采样率和应用；不依赖网络或 API。"
)
with st.expander("查看内置主题列表"):
    for entry in ai.offline.entries:
        st.markdown(f"- **{entry['title']}** · {entry['chapter']}")

st.markdown("### 按章节检索课程原文与内置知识")
chapters = list(dict.fromkeys([*rag.chapters(), *ai.offline_chapters()]))
filter_col, search_col = st.columns([0.9, 2.1])
with filter_col:
    chapter = st.selectbox("章节筛选", ["全部章节", *chapters], index=0)
with search_col:
    query = st.text_input("检索关键词或问题", placeholder="例如：奈奎斯特采样定理、频率分辨率、FIR 线性相位")
if query.strip():
    with st.spinner("检索中…"):
        hits = rag.search(
            query,
            top_k=6,
            chapter=None if chapter == "全部章节" else chapter,
        )
        builtin_hits = ai.search_builtin(query, top_k=8)
        if chapter != "全部章节":
            builtin_hits = [
                hit
                for hit in builtin_hits
                if chapter in hit.entry["chapter"] or hit.entry["chapter"] in chapter
            ]
    if not hits and not builtin_hits:
        st.info("没有找到足够相关的内容。可以换个关键词，或直接到“智能问答”用本地知识库提问。")
    if hits:
        st.caption(f"课程资料：找到 {len(hits)} 条相关片段。")
        citations = []
        for index, hit in enumerate(hits, start=1):
            citation = hit.citation
            citation["marker"] = f"片段{index}"
            citations.append(citation)
        render_citations(citations, expanded=True)
    if builtin_hits:
        st.caption(f"内置知识：找到 {len(builtin_hits)} 个主题。")
        for hit in builtin_hits[:4]:
            entry = hit.entry
            with st.container(border=True):
                st.markdown(f"**{entry['title']}**")
                st.caption(f"{entry['chapter']} · 本地条目")
                st.markdown(entry["summary"])
                with st.expander("关键公式与易错点"):
                    if entry["formulas"]:
                        for formula in entry["formulas"]:
                            st.markdown(f"$${formula['latex']}$$")
                            st.caption(formula["meaning"])
                    for mistake in entry["common_mistakes"]:
                        st.markdown(f"- {mistake}")
else:
    if chapters:
        st.caption("当前可用章节：" + " · ".join(chapters[:12]))
    st.caption("上传课程资料后，这里会同时检索原文片段和内置知识条目。")

if manifest.get("warnings"):
    with st.expander("索引构建提示"):
        for warning in manifest["warnings"]:
            st.warning(warning)

footer()
