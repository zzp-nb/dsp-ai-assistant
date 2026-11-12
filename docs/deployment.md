# 从零部署教程

这份教程面向没有专业运维经验的任课教师。按顺序做即可。先给结论：

- **只想快速把网址发给学生、能接受数据可能丢失**：用 Streamlit Community Cloud。
- **要保存一学期的课堂问题、调用记录和资料**：用 Docker + 持久磁盘（一台低成本云主机或支持磁盘的托管平台）。
- **不要在 Streamlit Cloud 上期待 SQLite 永久保存**，它没有持久卷。
- **默认可以完全离线**：内置 DSP 知识库与题库，不需要 DeepSeek Key；下面的 DeepSeek 配置是可选项。

---

## 一、部署前准备

### 1. 你需要的账号

| 账号 | 用途 | 费用 |
|---|---|---|
| GitHub | 存放代码、连接 Streamlit Cloud | 免费 |
| Streamlit Community Cloud | 运行网页 | 有免费额度，规则可能变化 |
| DeepSeek 开放平台（可选） | 在线 AI API；离线模式不需要 | 按 token 付费 |
| （可选）云主机/Docker 平台 | 持久化部署 | 通常每月几十元起 |

### 2. 你需要准备的内容

- 一个强班级密码（例如 12 位以上随机字符串）
- 一个不同的强教师密码
- 教师的 PPT/PDF（**不要**放进公开仓库）
- 可选：DeepSeek API Key（`sk-` 开头）

### 3. 检查本地环境

在项目目录运行：

```powershell
.\.venv\Scripts\python.exe scripts\check_environment.py
```

它会告诉你哪些配置还缺失。没有配置 Key 时，仍可检查目录、数据库和资料状态。

---

## 二、（可选）配置 DeepSeek

> 如果只用内置知识库，跳过这一节，并在 Secrets 或 `.env` 中设置 `DSP_OFFLINE_MODE=true`。不填 Key 也会自动离线。

1. 打开 <https://platform.deepseek.com/>，注册/登录。
2. 进入“API Keys”，创建一个 Key。Key 通常只显示一次，立即复制保存。
3. 在“充值/余额”确认账户有少量余额。没有余额时 API 会返回 402。
4. 不要把 Key 写进 `app.py`、截图、微信群、GitHub 或浏览器控制台。
5. 本项目只在服务端读取 `DEEPSEEK_API_KEY`，不会把它发送给浏览器。

本地写入 `.env`：

```dotenv
DEEPSEEK_API_KEY=sk-你的真实Key
DSP_OFFLINE_MODE=false
```

Streamlit Cloud 写入 Secrets（注意 TOML 格式，不要加代码块）：

```toml
DEEPSEEK_API_KEY = "sk-你的真实Key"
DSP_OFFLINE_MODE = false
```

如果 Key 曾经出现在公开仓库或聊天记录里，请立即到 DeepSeek 控制台撤销并重新生成。

价格：

- 本项目用 `config/pricing.json` 估算费用，默认值是示例，不是财务报价。
- DeepSeek 可能随时调价，请以 <https://api-docs.deepseek.com/quick_start/pricing> 为准。
- 教师端“使用统计与费用”显示的是按 token 估算的金额，实际扣费以 DeepSeek 账单为准。

---

## 三、把代码上传到 GitHub

### 方案 A：使用 Git 命令（推荐，前提是已安装 Git）

在项目根目录：

```bash
git init
git add .
git commit -m "DSP AI teaching assistant v1"
git branch -M main
git remote add origin https://github.com/你的用户名/dsp-ai-assistant.git
git push -u origin main
```

`.gitignore` 已经排除：

- `.env`、`.streamlit/secrets.toml`
- `.venv`
- `data/course_materials/*`
- `data/vector_store/*`
- `data/database/*`

推之前可以检查：

```bash
git status
git ls-files | findstr /i "env secrets course_materials"
```

Windows 没有 `findstr` 时用 `git ls-files` 人工检查。**不要在仓库里看到 Key、密码、PPT、PDF、数据库。**

### 方案 B：不使用命令行（GitHub 网页）

1. 登录 GitHub，点右上角 “+” → “New repository”。
2. 仓库名如 `dsp-ai-assistant`；选择 Public（Streamlit 免费方案通常需要公开仓库）；不要勾选自动生成 README，因为项目已有。
3. 创建后点 “Add file” → “Upload files”。
4. 上传项目源码，**不要上传**：
   - `.env`
   - `.venv/`
   - `data/course_materials/` 里的课件
   - `data/database/` 里的 `.db`
   - `.streamlit/secrets.toml`
5. GitHub 网页对隐藏文件夹不友好。若 `.streamlit/config.toml` 没上传成功，在仓库里手动 “Add file → Create new file”，文件名填 `.streamlit/config.toml`，粘贴文件内容。
6. `.gitignore` 对网页上传不生效，必须靠你手动排除。

> 公开仓库意味着全世界都能看到代码。代码公开没问题，**密钥和课程资料不能公开**。

---

## 四、部署到 Streamlit Community Cloud

### 1. 创建 App

1. 打开 <https://share.streamlit.io/>，用 GitHub 登录。
2. 点 “Create app” / “New app”。
3. 选择你的仓库、分支 `main`、主文件路径 `app.py`。
4. 如果界面有 “Advanced settings”，Python 版本选 3.12。
5. 先不要急着 Deploy，配置 Secrets。

### 2. 配置 Secrets

在 App 的 “Settings → Secrets”，粘贴：

```toml
DSP_CLASS_PASSWORD = "替换成强班级密码"
DSP_TEACHER_PASSWORD = "替换成另一个强教师密码"

# 完全离线：不需要 DeepSeek Key，问答/推导/习题使用内置知识库
DSP_OFFLINE_MODE = true

# 只有需要在线生成时，才取消注释并填写：
# DEEPSEEK_API_KEY = "sk-你的Key"
# DSP_OFFLINE_MODE = false
```

保存后 Deploy/Re-run。

**不要在 Cloud 上设置 `DSP_DATA_DIR=/data`**：Streamlit Cloud 没有这个持久卷，目录可能不可写。默认项目内 `data/` 可以在运行期间使用，但重启后会重置。

### 3. 首次上线检查

1. 打开公网网址，确认首页出现。
2. 教师入口登录，确认“本地离线”。
3. 在“智能问答”提一个 DSP 问题，确认有本地知识库回答。
4. 上传 PPT/PDF，重建索引，抽查引用。
5. 用无痕窗口模拟学生登录，提交一个问题。
6. 教师端选择问题并展示，打开课堂大屏确认。
7. 把网址发给学生。

### 4. 免费托管的现实限制

- **休眠/冷启动**：一段时间无人访问后会休眠，再次访问需要等待。
- **文件系统 ephemeral**：SQLite、上传资料、索引可能在重启/重新部署后丢失。
- **资源有限**：大 PDF/大量资料可能解析慢或内存不足。
- **公开仓库**：免费方案通常要求代码公开。
- **平台规则会变化**：免费额度、休眠策略、资源上限不保证永久不变。

因此：

- 课堂演示、短期试用：Cloud 够用。
- 一学期持续使用：请在每次冷启动后重新上传资料并建索引，或改用持久化部署。
- 不要把 Cloud 上的 SQLite 当成唯一成绩/课堂记录来源。

---

## 五、低成本持久化部署（推荐正式使用）

### 方案：Docker + 持久磁盘

适合一台小型云主机、实验室服务器、支持 Docker 的托管平台。项目已经包含 `Dockerfile` 和 `docker-compose.yml`。

#### 1. 服务器准备

- 安装 Docker 与 Docker Compose
- 开放 8501 端口（或只开放 80/443，用反向代理）
- 把项目代码放进服务器目录

#### 2. 配置环境变量

```bash
cp .env.example .env
nano .env
```

填写：

```dotenv
DSP_CLASS_PASSWORD=强班级密码
DSP_TEACHER_PASSWORD=强教师密码
DSP_OFFLINE_MODE=true
DSP_DATA_DIR=/data
# 只有在线模式才需要：
# DEEPSEEK_API_KEY=sk-...
```

#### 3. 启动

```bash
docker compose up -d --build
docker compose logs -f
```

访问：

```text
http://服务器IP:8501
```

`docker-compose.yml` 已把宿主机的 `./data` 挂载到容器 `/data`，所以数据库、课程资料、索引会保留。

#### 4. 备份

最稳妥的方式是先停止容器，再复制数据：

```bash
docker compose stop
tar -czf dsp-backup-$(date +%F).tar.gz data/
docker compose start
```

把备份文件下载到另一台机器。恢复时解压回 `data/` 再启动。

#### 5. HTTPS 与域名（可选）

不要直接把 8501 裸奔到公网。可以用 Caddy/Nginx 做 HTTPS 反向代理。Caddy 示例：

```caddyfile
dsp.example.edu.cn {
    reverse_proxy 127.0.0.1:8501
}
```

这需要域名和服务器；第一版不强制。若只在校园网内使用，可让学校网络中心协助。

### 其他托管平台

- **Render**：可以用 Docker 部署，但**持久磁盘是付费能力**，免费实例会休眠且没有持久盘。选择 Docker、添加 Disk 挂载到 `/var/data`，设置 `DSP_DATA_DIR=/var/data`，健康检查路径 `/_stcore/health`。
- **Fly.io**：支持 volume，配置比 Streamlit Cloud 复杂，适合愿意看文档的老师。
- **Supabase/Postgres/对象存储**：本项目预留了 `storage.py` 和数据库路径接口，但**v1 没有实现 Postgres/对象存储适配器**。不要以为改一个环境变量就能把 SQLite 变成 Supabase；需要写适配代码并迁移。

---

## 六、课程资料如何安全存放

### 公开 GitHub

绝对不要提交：

- 教师原始 PPT/PDF
- 教材扫描件
- 学生问题/对话数据库
- `.env`、`secrets.toml`
- API Key

`.gitignore` 已排除，但网页上传不受 `.gitignore` 保护，需要手动确认。

### Streamlit Cloud

- 运行时通过教师端上传到 `data/course_materials/`
- 只在当前实例生命周期内有效
- 不要在 Secrets 里塞大 PDF（不适合，且有大小限制）

### 持久服务器

- 课程资料放在宿主机私有目录，挂载给容器
- 设置文件权限，只允许运行应用的系统用户读取
- 定期备份
- 不要把资料目录放到公开的静态网站目录

### 版权

只上传你有权使用的课程资料。教材 PDF 的公开传播可能涉及版权；本系统仅做课程内部检索，不改变原始版权归属。

---

## 七、更新与回滚

### Streamlit Cloud

1. 修改 GitHub 仓库并 push。
2. Cloud 会自动重新部署，或在界面点 Reboot。
3. 重新检查 Secrets 和资料（因为文件系统可能已重置）。

### Docker

```bash
git pull
docker compose up -d --build
```

数据库结构目前通过 `CREATE TABLE IF NOT EXISTS` 初始化，v1 没有复杂迁移。升级前先备份 `data/`。

---

## 八、安全清单

- [ ] 班级密码、教师密码是强随机值，且不相同
- [ ] 离线模式不需要 API Key；在线模式才把 Key 放在服务端 Secrets/.env
- [ ] GitHub 仓库没有 `.env`、`secrets.toml`、课程资料、数据库
- [ ] 在线模式才设置学生每日额度和全班每日额度
- [ ] 在线模式已测试 401（Key 错误）、402（余额不足）提示
- [ ] 已确认学生打不开教师管理页
- [ ] 课堂大屏只显示教师选择的问题
- [ ] 服务器使用 HTTPS，未把 8501 直接暴露给全网
- [ ] 定期备份 `data/`
- [ ] 在线模式定期查看 DeepSeek 余额和调用量

---

## 九、常见故障

**页面提示“服务端尚未配置 DeepSeek API Key”**  
不需要处理；没有 Key 会自动使用本地知识库。若要在线调用，才填写 `DEEPSEEK_API_KEY` 并设置 `DSP_OFFLINE_MODE=false`。

**登录一直失败**  
确认 `.env`/Secrets 里的 `DSP_CLASS_PASSWORD` 和 `DSP_TEACHER_PASSWORD`。修改后必须重启 Streamlit 进程。

**上传了资料但问答没有引用**  
上传只是保存文件；必须在“课程知识库”点“重建课程索引”。

**索引里没有扫描 PDF 的内容**  
扫描件没有文本层。使用 `.ocr.txt` 侧车补录，或先用 OCR 软件生成可搜索 PDF。

**Streamlit Cloud 重启后资料和记录消失**  
这是免费托管的 ephemeral 文件系统，不是代码 bug。改用持久卷部署，或重新上传/建索引。

**API 返回 401**  
Key 错误或被撤销。到 DeepSeek 控制台重新生成。

**API 返回 402**  
账户余额不足。充值后重试。

**API 返回 429**  
请求太频繁。稍等一分钟；同时检查是否额度设置过宽。

**页面很慢**  
大 PDF/大量资料首次索引会慢。查看 Streamlit 日志和内存；把资料拆分、减少页数，或升级持久服务器配置。

**`ModuleNotFoundError`**  
依赖没装全：`pip install -r requirements.txt`。Cloud 上检查 requirements.txt 是否已提交。

---

## 十、最小上线路径（总结）

1. 本地运行通过。
2. 检查 `.gitignore`，确认没有密钥/资料。
3. 推到 GitHub。
4. Streamlit Cloud 连接仓库，填密码 Secret；离线模式再填 `DSP_OFFLINE_MODE = true`。
5. 教师登录 → 确认本地离线 → 上传资料 → 建索引。
6. 学生无痕窗口测试 → 课堂大屏测试。
7. 发网址。
8. 如果要用一学期：尽快迁移到 Docker + 持久磁盘，并建立备份习惯。

不要承诺免费平台永久免费或永久稳定。正式教学数据请按持久化方案部署。
