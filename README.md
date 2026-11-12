# DSP AI 智能教学助手

面向大学《数字信号处理》课程的智能教学与自主学习平台。教师用班级密码组织课堂，学生免注册进入；支持 **完全离线运行**：内置 DSP 知识库、公式推导和习题库，不联网、不需要 DeepSeek API；也可以选择接入 DeepSeek 获得更自由的生成式回答。

> 这是一个可实际运行的 Streamlit 应用，不是界面演示。核心功能均有后端实现、数据库记录与自动化测试。

---

## 1. 当前完成情况

| 模块 | 状态 | 说明 |
|---|---|---|
| 首页与导航 | 已完成 | 深蓝/白/浅灰主题、六大功能入口、移动端适配 |
| 学生/教师权限 | 已完成 | 班级密码、独立教师密码、服务端校验、页面守卫 |
| AI 智能问答 | 已完成 | 三种讲解模式、连续追问、LaTeX；离线知识库与可选 DeepSeek |
| 离线知识库 | 已完成 | 32 个 DSP 主题、符号/推导/例子/易错点，断网可用 |
| RAG 课程知识库 | 已完成 | PDF/PPTX 文本解析、章节/页码、混合检索、资料引用 |
| 公式推导 | 已完成 | 本地条目分步推导；在线模式可使用 DeepSeek |
| 智能习题 | 已完成 | 30 道内置题，六种题型；离线组卷与结构校验 |
| 信号仿真 | 已完成 | 采样/混叠、卷积、FFT、FIR、IIR，全部实时计算 |
| 课堂互动 | 已完成 | 学生提交、状态查看、教师选择、投影、AI 回答开关 |
| 课堂大屏 | 已完成 | 3 秒自动刷新，只展示教师明确选择的内容 |
| 教师管理 | 已完成 | 问题面板、使用量、Token、费用估算、额度设置、API 连接测试 |
| 费用控制 | 已完成 | 在线模式的额度、输入/输出限制、原子预占、失败记录 |
| 本地/服务器部署 | 已完成 | `.env`、Streamlit Secrets、Docker + 持久卷 |
| Streamlit Cloud | 已准备 | 配置与教程齐全；持久化限制已明确说明 |
| 真实 DeepSeek 调用 | 已验证 | 当前默认离线；切换在线并填入 Key 后可用 |

### 诚实的能力边界

- **PPT 图片、截图、公式图片、扫描 PDF 不做 OCR**。第一版只提取文本层；图片页会明确提示，可上传 `.ocr.txt` 人工补录。
- **没有学生账号体系**。学号/昵称仅用于课堂标识和额度；换浏览器可能获得新会话额度，因此还有全班总额度兜底。这不是强身份安全边界。
- **课堂实时性为 3 秒轮询**，不是 WebSocket 弹幕。稳定、够用、易维护。
- **云端 SQLite/上传文件可能丢失**。Streamlit Community Cloud 没有持久卷；正式长期使用请用 Docker + 持久磁盘，详见 [部署教程](docs/deployment.md)。
- **AI 仍可能出错**。系统校验了引用来源和习题结构，但教师/学生仍需核对公式和答案；不确定时以教材和教师讲解为准。
- 默认价格是示例配置，财务数据以 DeepSeek 官方账单为准。

---

## 2. 技术栈

- Python 3.12 + Streamlit
- **完全离线的内置 DSP 知识库与题库**（默认模式）
- DeepSeek Chat Completions API（可选；OpenAI 兼容协议，服务端直连）
- PyMuPDF（PDF）、python-pptx（PPTX）
- NumPy / SciPy / Matplotlib
- SQLite（WAL，多连接）
- 本地哈希 TF-IDF 向量 + BM25 关键词混合检索（不依赖外部 Embedding API）

不引入 LangChain、向量数据库、Redis、Celery 等重型依赖。几十人班级规模下，这套结构更便宜、更容易维护。

### 离线模式

应用默认优先使用本地内容：

- 32 个 DSP 知识主题：信号与系统、采样/混叠、Z 变换/ROC、DTFT/DFT/FFT、窗函数、FIR/IIR、滤波器结构、多采样率、应用。
- 30 道内置习题，覆盖单项选择、多项选择、填空、判断、计算、简答。
- 每个知识条目包含：直觉解释、专业解释、核心公式、分步推导、例子、常见错误。
- 本地混合检索；不需要下载模型、不需要联网、不消耗 Token。
- 上传的 PPT/PDF 仍会在本机解析；离线回答可以同时引用课程原文片段。

启用方式：

```dotenv
DSP_OFFLINE_MODE=true
```

不填 `DEEPSEEK_API_KEY` 时也会自动进入离线模式。

> 注意：离线模式不需要互联网来生成回答，但如果要通过 Streamlit Cloud 让外地学生访问，访问网页本身仍需要网络。

---

## 3. 快速开始（本地）

### 3.1 已配置好的当前工作区

本项目的虚拟环境和本地演示配置已经创建：

```powershell
cd C:\Users\Admin\Documents\deepseek-harness\default-workspace\dsp-ai-assistant
.\.venv\Scripts\python.exe -m streamlit run app.py
```

浏览器打开 `http://localhost:8501`。

当前本地 `.env` 中已经配置了班级密码和教师密码。为避免把真实密码写进公开仓库，README 不列出具体值；请查看本地 `.env`，并在发给学生前改成强密码。

> `.env` 只用于本机。上线时不要把 `.env` 上传 GitHub，应在 Streamlit Secrets 中配置密码。
> 当前本地配置为 **离线模式**：问答、公式推导和习题直接使用内置知识库，不需要 DeepSeek Key，也不会联网或产生 Token 费用。

### 3.2 从零安装（另一台电脑）

1. 安装 Python 3.11 或 3.12（Windows 安装时勾选 “Add Python to PATH”）。
2. 打开 PowerShell：

```powershell
cd dsp-ai-assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
python -m streamlit run app.py
```

macOS / Linux：

```bash
cd dsp-ai-assistant
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env
streamlit run app.py
```

如果 PowerShell 不允许激活脚本，也可以不激活，直接：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

### 3.3 最小配置

编辑 `.env`：

```dotenv
DSP_CLASS_PASSWORD=你的班级密码
DSP_TEACHER_PASSWORD=你的教师密码
DEEPSEEK_API_KEY=sk-你的Key
```

也可以使用 `.streamlit/secrets.toml`（适合 Streamlit Cloud）：

```toml
DSP_CLASS_PASSWORD = "你的班级密码"
DSP_TEACHER_PASSWORD = "你的教师密码"
DEEPSEEK_API_KEY = "sk-你的Key"
```

配置读取优先级：环境变量 > Streamlit Secrets。密钥只在服务端进程中使用，不会写入页面或浏览器。

---

## 4. 第一次使用流程

### 教师

1. 首页选择“教师入口”，输入教师密码。
2. 进入“教师管理 → API 与系统”，确认运行模式为“本地离线”；离线模式不需要测试 API。
3. 进入“课程知识库”，上传 PPT/PDF，点击“重建课程索引”。
4. 检查“已导入资料”中的页数、文本块、解析状态。
5. 如果切换到在线 DeepSeek，再在“调用额度设置”设置学生与全班每日上限。
6. 打开“课堂大屏”到投影仪；学生提交问题后，在“课堂问题”中选择展示。

### 学生

1. 首页输入班级密码进入；学号/昵称可留空。
2. 在“智能问答”选择通俗/专业/数学推导模式提问，支持连续追问。
3. 在“课程知识库”按章节或关键词检索原文。
4. 在“公式推导”“智能习题”中练习。
5. 在“信号仿真”调参数观察采样、混叠、卷积、频谱和滤波器。
6. 在“课堂互动”提交问题，查看教师处理状态。

---

## 5. 课程资料导入规则

### 支持

- `.pptx`：文本框、表格、组合形状文字、讲稿备注
- `.pdf`：文本层、PDF 目录/页码
- `.txt` / `.md`：人工补充材料
- 同名侧车文件：`lecture.pdf.ocr.txt`、`lecture.pptx.ocr.txt`

### 不假装支持

- PPT 中图片内文字
- 扫描 PDF 的整页图像
- 公式图片的结构化还原（例如把截图变成可计算公式）

侧车文件格式：

```text
[[PAGE 12]]
这里是第 12 页扫描内容的人工转录。

[[SLIDE 7]]
这里是第 7 张幻灯片图片中的文字。
```

上传入口：教师端“课程知识库 → 图片 / 扫描页文字补录”。

详细说明见 [docs/material_import.md](docs/material_import.md)。

> **版权**：不要将教师的原始 PPT、教材 PDF 提交到公开 GitHub。`.gitignore` 已排除 `data/course_materials/*`。

---

## 6. 权限、隐私与额度

### 密码

- 班级密码、教师密码均从环境变量/Secrets 读取，代码中没有默认硬编码密码。
- 比较使用 `hmac.compare_digest`，避免简单时序差异。
- 登录失败 5 次会在当前浏览器会话内锁定 30 秒。这是课堂级防护，不是企业级认证。

### 学生隐私

- 没有个人账号；学号/昵称可选。
- 普通学生只能看到自己当前会话提交的课堂问题。
- 教师统计页不展示学生私人对话原文。
- 课堂大屏只展示教师明确选择的单个问题，不显示学生姓名。

### 额度（仅在线模式）

- **离线模式不消耗 API 额度，也不产生 Token 费用。**
- 在线模式下，每次问答/推导/习题/课堂回答/连接测试都先在数据库原子预占一次调用。
- 学生每日上限、全班每日上限均可在教师端修改。
- 单次输入字符数、单次输出 Token 数有硬限制。
- 重复点击有 6–8 秒的相同请求拦截。
- API 调用失败也会被记录；失败请求仍占用一次预占额度（避免通过失败请求无限重试）。
- 无账号模式无法绝对防止换浏览器绕过个人额度，**全班总额度是最终兜底**。

费用估算：

```text
config/pricing.json
```

价格不写死在代码中。DeepSeek 调价后修改该文件并重启应用。默认值只是示例，需以[官方价格页](https://api-docs.deepseek.com/quick_start/pricing)为准。

---

## 7. 数据与持久化

默认目录：

```text
data/
├── course_materials/   # 教师上传的 PPT/PDF
├── vector_store/       # chunks.jsonl / vectors.npz / bm25.json / manifest.json
└── database/dsp.db     # SQLite
```

可通过以下环境变量改变：

```dotenv
DSP_DATA_DIR=/var/data/dsp
DSP_DATABASE_PATH=/var/data/dsp/database/dsp.db
DSP_MATERIALS_DIR=/var/data/dsp/course_materials
DSP_VECTOR_DIR=/var/data/dsp/vector_store
```

### 重要

- **Streamlit Community Cloud 没有持久卷**。休眠、重启、重新部署后 SQLite、上传资料和索引会丢失。每次冷启动后可能需要重新上传资料并重建索引。
- **本地电脑**：文件会保留。
- **Docker/VPS + 挂载卷**：文件会保留，适合一学期使用。项目已提供 `Dockerfile` 与 `docker-compose.yml`。
- **不要把 SQLite 当成多实例共享数据库**。本方案按单实例、几十人设计。

详见 [部署教程](docs/deployment.md)。

---

## 8. 课堂展示机制

1. 学生提交问题 → 写入 `classroom_questions`，状态 `pending`。
2. 问题**不会自动投影**。
3. 教师打开“教师管理 → 课堂问题”，点击“生成 AI 回答”。
4. 教师选择“仅展示问题”或“展示问题 + AI”。
5. 大屏页面每 3 秒读取一次数据库，只显示 `is_displayed=1` 的问题。
6. 教师可随时关闭展示，或单独切换“是否展示 AI 回答”。

没有引入 WebSocket 或消息队列。课堂投影的使用场景下，3 秒延迟可以接受，换来的是更低的故障率和维护成本。

---

## 9. 测试

已覆盖：

- 密码与身份工具
- 费用计算
- SQLite 额度、会话隔离、课堂展示唯一性
- PDF/PPTX 解析、页码、OCR 侧车
- 索引构建、检索、章节过滤、重建
- 习题 JSON 结构与答案格式校验
- DeepSeek 客户端成功/401/5xx/超时/空回答
- AI 服务配额、日志、连续对话
- 采样、混叠、卷积、FFT、FIR、IIR 数值正确性
- 全部 Streamlit 页面渲染、登录、学生/教师权限
- Mock 模型下的问答、习题生成、课堂提问与投影全流程
- 本地资料存储接口

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

开发依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

> 本机实际验证使用 Streamlit 1.66.1、Python 3.12.14，当前 **74 项自动化测试全部通过**。真实 DeepSeek 连接也已验证；默认离线模式不使用 API。测试同时覆盖了 Mock 请求、错误映射和计费链路。

---

## 10. 项目结构

```text
dsp-ai-assistant/
├── app.py                       # 首页、登录、角色入口
├── pages/
│   ├── 1_智能问答.py
│   ├── 2_课程知识库.py
│   ├── 3_公式推导.py
│   ├── 4_智能习题.py
│   ├── 5_信号仿真.py
│   ├── 6_课堂互动.py
│   ├── 7_教师管理.py
│   └── 8_课堂展示.py
├── core/
│   ├── config.py                # 配置与 Secrets
│   ├── paths.py                 # 数据目录布局
│   ├── auth.py                  # 密码、会话、身份
│   ├── database.py              # SQLite、额度、课堂问题
│   ├── deepseek_client.py       # DeepSeek HTTP 客户端（可选）
│   ├── offline_tutor.py         # 离线检索、讲解、推导、组卷
│   ├── ai_service.py            # 在线/离线分流、配额、日志
│   ├── prompts.py               # 在线中文教学提示词
│   ├── quiz.py                  # 习题 JSON 严格校验
│   ├── cost_tracker.py          # 在线费用估算
│   ├── document_loader.py       # PDF/PPTX/TXT 解析与切块
│   ├── embedding.py             # 可替换 Embedding 接口
│   ├── rag_engine.py            # BM25 + TF-IDF 混合检索
│   └── storage.py               # 可替换资料存储接口
├── knowledge/
│   ├── dsp_entries.py           # 32 个内置 DSP 主题
│   └── dsp_quiz_bank.py         # 30 道内置习题
├── dsp/
│   ├── sampling.py
│   ├── convolution.py
│   ├── fft.py
│   └── filters.py
├── ui/
│   ├── theme.py                 # 视觉设计与侧边栏
│   ├── guard.py                 # 页面权限
│   ├── runtime.py               # 会话与依赖装配
│   ├── content.py               # 引用/状态组件
│   └── plots.py                 # Matplotlib 图表
├── data/                        # 运行时数据（默认 gitignore）
├── docs/
│   ├── deployment.md
│   ├── teacher_guide.md
│   └── material_import.md
├── tests/
├── scripts/
│   ├── check_environment.py
│   └── build_index.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── .streamlit/
    ├── config.toml
    └── secrets.toml.example
```

---

## 11. 部署到公网

详细零基础教程见 **[docs/deployment.md](docs/deployment.md)**，包括：

- GitHub 上传（含不使用命令行的网页上传方式）
- Streamlit Community Cloud 部署
- Secrets 配置
- 免费托管的休眠/资源/持久化限制
- Docker + 持久磁盘的低成本长期方案
- 课程资料安全存储
- 上线前检查清单

最短路径：

1. 把代码推到 GitHub（不要带 `.env`、`.venv`、`data/` 里的资料）。
2. 在 share.streamlit.io 新建 App，入口 `app.py`。
3. 在 Secrets 填班级密码、教师密码；离线模式再填 `DSP_OFFLINE_MODE = true`，不需要 DeepSeek Key。
4. 部署后先登录教师端，确认“本地离线”，上传资料、建索引。
5. 把公网网址发给学生。

> 免费平台不承诺永久免费或永久稳定。正式课程数据请使用带持久磁盘的部署方式。

---

## 12. 常见问题

**Q：页面提示“服务端尚未配置 DeepSeek API Key”？**  
A：不需要处理。没有 Key 时会自动使用本地知识库。若要在线调用，才填写 `DEEPSEEK_API_KEY` 并把 `DSP_OFFLINE_MODE` 设为 false。

**Q：上传资料后问答没有引用？**  
A：上传只保存文件，必须再点“重建课程索引”。确认资料状态是“已索引”。

**Q：PDF/PPT 有内容但没被检索到？**  
A：可能是图片/扫描页。查看“图片页”数量，并使用 OCR 侧车文本补录。

**Q：AI 回答里没有页码？**  
A：系统会把真实检索片段和页码显示在“查看课程资料依据”中，不依赖模型自己编页码。若资料不足，会明确标注为 AI 补充。

**Q：Streamlit Cloud 重启后数据没了？**  
A：这是平台 ephemeral 文件系统，不是程序 bug。改用持久磁盘部署，或在每次冷启动后重新上传资料并重建索引。

**Q：学生换浏览器绕过每日额度怎么办？**  
A：离线模式没有 API 额度，可忽略。在线模式下无账号只能做课堂级限制，请设置全班每日总额度，并说明使用规范。

**Q：为什么仿真图坐标是英文？**  
A：为了保证在 Streamlit Cloud 的 Linux 容器里不出现中文字体缺字（豆腐块），图表坐标使用英文，中文解释放在页面正文。若要改成中文，可安装 Noto Sans CJK 并配置 Matplotlib 字体。

---

## 13. 安全提醒

上线前至少完成：

- [ ] 更换示例密码为强随机密码
- [ ] 离线模式不需要 API Key；若启用在线，Key 只放在服务端 Secrets
- [ ] 确认 GitHub 仓库没有 `.env`、`data/course_materials`、`secrets.toml`
- [ ] 在线模式才需要设置学生与全班每日额度
- [ ] 课程资料只存放在私有目录或私有卷
- [ ] 若启用在线，定期检查 DeepSeek 余额和调用量
- [ ] 若 Key 泄露，立即在 DeepSeek 控制台撤销并重新生成

---

## 14. 说明

本项目是一个课程教学辅助工具，AI 输出不构成学术结论或评分依据。教师应抽查 RAG 引用、习题答案和公式推导；学生应独立完成作业和考试。

如需扩展：私有化 Embedding、Supabase/Postgres 持久化、OCR、更多仿真模块，均可沿现有 `embedding.py`、`storage.py`、`database.py` 接口替换，不需要重写页面。
