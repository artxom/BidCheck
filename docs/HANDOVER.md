# BidGuard（标书智检）工程交接与迭代维护手册

> **文档定位**：本文件为项目的**权威工程交接基准（Single Source of Truth）**。依据项目维护铁律，**每次阶段性开发或优化执行完毕后，必须通过全部自动化测试、同步更新本交接文档的架构说明与第八章《里程碑交接台账》，并提交同步至 GitHub 远端仓库。**

- **当前版本**：`v0.6.0`
- **主干分支**：`main`
- **远端仓库**：`https://github.com/artxom/BidCheck.git`
- **技术栈**：Python 3.11+ / FastAPI / SQLite (WAL) / lxml / PyMuPDF / AsyncOpenAI + React 19 / TypeScript / Vite 6 / Tailwind CSS v4 + PyInstaller (`--onedir`) & GitHub Actions Windows CI

---

## 一、项目目标与核心设计准则

### 1.1 业务核查边界
1. **查“有无实质响应”与“形式红线”，不评判方案文笔优劣**：聚焦资格审查项、废标红线、商务资信评分点、技术服务评分点、采购需求（功能/非功能/实施维保）及第四章标准文书格式。
2. **多标段精准隔离**：自动从文件名、封面及目录识别分标号（如 `C标段`），规划清单时自动剔除非目标标段的专属评分表与需求表。
3. **按需多模态验图**：仅对营业执照、资质认证、审计财报、完税社保、身份证、业绩合同扫描件等图片证明条款启用视觉模型核验，避免无效视觉 Token 浪费。
4. **增量复检闭环**：支持基于 SQLite 条目级检查点进行全量并发核查或仅针对 `partial` / `missing` / `failed` 条目快速增量复检。

### 1.2 交互与视觉设计准则（macOS 原生克制风格）
1. **单一对话主控**：用户所有意图表达、清单裁剪、标段切换与复检指令均只与 **Master Agent** 沟通。
2. **前台透明可观测**：顶部状态胶囊（Activity Capsule）实时推送当前阶段、完成度百分比、滑动窗口剩余时间（ETA）、活跃并发数、累计 Token 与费用明细。
3. **克制文案与质感分层**：剔除一切教学式长句提示词，采用短标签与高信噪比布局；界面支持 **浅色（Light）/ 深色（Dark）/ 自动跟随系统（System）** 三态无缝切换，具备毛玻璃材质（Vibrancy）、微高光内描边与原生分段控件质感。

---

## 二、系统架构与模块职责矩阵

### 2.1 全链路数据流架构

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                     Frontend SPA (React 19 + Tailwind v4)                    │
│  ┌──────────────┐   ┌─────────────────────────┐   ┌───────────────────────┐  │
│  │   Sidebar    │   │     MasterChatPane      │   │     InspectorPane     │  │
│  │ 项目切换/缓存 │   │ 双文档槽 + Master 会话流 │   │  实况  │  报告 │ 原文  │  │
│  └──────────────┘   └───────────┬─────────────┘   └───────────┬───────────┘  │
│                                 │ REST + EventSource (SSE)    │              │
└─────────────────────────────────┼─────────────────────────────┼──────────────┘
                                  ▼                             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                        FastAPI Monolith (backend/main.py)                    │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌────────────────────┐  │
│  │   Document Engine    │  │  Multi-Agent Kernel  │  │   LLM & SSE Bus    │  │
│  │ • docx_parser (lxml) │  │ • master_agent.py    │  │ • AsyncOpenAI 网关 │  │
│  │ • pdf_parser (fitz)  │  │ • worker_engine.py   │  │ • 四角色独立并发锁 │  │
│  │ • 6类固有红线扫描器   │  │ • report_agent.py    │  │ • Token/费用台账   │  │
│  │ • BM25+标题层级检索  │  │ • html 交互快照导出  │  │ • 动态 ETA 估算器  │  │
│  └──────────┬───────────┘  └──────────┬───────────┘  └─────────┬──────────┘  │
│             └─────────────────────────┼────────────────────────┘             │
│                                       ▼                                      │
│            SQLite WAL (data/bidguard.db) + AST/JPEG/WebP 按需缓存            │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 后端代码模块清单

| 路径 | 核心职责 |
| :--- | :--- |
| `launcher.py` | 独立桌面启动器：Windows 无控制台流重定向、`find_available_port` 端口探测、Edge `--app=` 独立窗口与 `tkinter` 控制窗、CI `--self-test` 冒烟验证 |
| `backend/main.py` | FastAPI 生命周期初始化（`APP_VERSION` / `/api/health`）、CORS、挂载四大 API 路由及托管 `frontend/dist` 单页应用 |
| `backend/config.py` | `resolve_runtime_paths` 源码/PyInstaller `_MEIPASS` 冻结双模式路径解析、8 家主流模型供应商预设、参考单价目录（`MODEL_PRICING_RULES`）、视觉能力推断（`infer_vision_capability`）与四角色定义 |
| `backend/schemas.py` | Pydantic 核心契约（`AppSettings`、`ChecklistItem`、`TelemetrySnapshot` 含 `estimated_plan_cost`、`InspectionReport`、`ProjectDetail`） |
| `backend/db.py` | SQLite WAL 连接池锁管理、项目 CRUD、检查项断点持久化、会话历史与 `token_ledger` 聚合统计 |
| `backend/parsers/docx_parser.py` | 原生 OOXML 流式解析段落/表格/`<a:blip>` 图片引用，章节树状态机保护（防普通 `附件：` 或标段子标题越权弹出章节点），结合目录 `PAGEREF` 锚定页码并懒转码压缩 JPEG |
| `backend/parsers/pdf_parser.py` | 基于 PyMuPDF (`fitz`) 的 PDF 书签大纲/字号启发式分章（同步应用章级与标段层级保护）、文本表格提取与内嵌图按需转码 |
| `backend/parsers/indexer.py` | 封面/标段元数据提取、6 类零 Token 确定性红线扫描器、合同过滤瘦身与全书紧凑骨架目录（`build_response_outline_summary`）、AST 版本化缓存 |
| `backend/llm/gateway.py` | `LLMGateway`（四角色路由、`/models` 能力与清单拉取、`reasoning_effort="low"` 与 HTTP 400 自动降级、`finish_reason="length"` 防盲目重试、实时单次遥测广播）与 `ProjectEventBus` |
| `backend/llm/prompts.py` | 针对中国大陆招投标定制的四角色 System Prompts（规划、文本核查、视觉验图、报告总装、会话控制） |
| `backend/agents/master_agent.py` | 0-Token 上传预检确认（`emit_document_precheck`）、双文档规划拆解、基于真实检索章节字数与角色单价的 `_estimate_plan_metrics` 预估、任务锁与 `/cancel` 取消控制 |
| `backend/agents/worker_engine.py` | 异步并发逐项核查（含 `asyncio.CancelledError` 安全回退）、确定性致命占位符强制降级硬锁、按需多模态验图 |
| `backend/agents/report_agent.py` | 全局响应统计、就绪度评分计算、封标风险结论汇编（含无 API 异常时的确定性兜底报告） |
| `backend/exporters/html_exporter.py` | 真同源 React + Tailwind v4 单文件交互式静态 HTML 报告导出器：内联编译产物与 `#bidguard-report-snapshot` JSON、`source_key` 去重并发 WebP 转码缓存、路径脱敏与防脚本注入转义 |
| `backend/exporters/docx_exporter.py` | 使用 `python-docx` 生成正式排版 Word 核查报告（保留接口向后兼容） |
| `backend/exporters/xlsx_exporter.py` | 使用 `openpyxl` 生成双 Sheet Excel 整改销项表（保留接口向后兼容） |
| `packaging/` & `scripts/build_windows.ps1` | Windows `.ico` 多尺寸图标生成、`packaging/bidguard.spec`（`--onedir` 捆绑 `frontend/dist` / `docx` / `certifi` / `pymupdf`）与本地一键打 `BidGuard-Windows-x64.zip` |
| `.github/workflows/release.yml` | GitHub Actions `windows-latest` 流水线：前端编译 → `pytest` 门禁 → PyInstaller 打包 → `BidGuard.exe --self-test` 冒烟 → 自动发布 `BidGuard-Windows-x64.zip` 至 GitHub Release |
| `backend/routers/*.py` | `projects.py`（8MB 流式上传、样本挂载、章节/图片预览）、`chat_stream.py`（对话、运行、SSE）、`reports.py`（导出）、`settings.py`（配置与连通性测试） |

### 2.3 前端代码模块清单

| 路径 | 核心职责 |
| :--- | :--- |
| `frontend/index.html` | 页面骨架与首屏防闪烁（FOUC-free）深浅色模式同步脚本 |
| `frontend/src/theme.ts` | `useTheme` 状态钩子：管理 `light` / `dark` / `system` 三态、`localStorage` 持久化与系统 `prefers-color-scheme` 实时监听 |
| `frontend/src/index.css` | Tailwind v4 `@custom-variant dark` 类驱动声明及 macOS 材质样式体系（`.macos-toolbar`、`.macos-sidebar`、`.macos-card`、`.macos-popover`、`.macos-segmented` 等） |
| `frontend/src/snapshot.ts` | 离线静态 HTML 快照适配器：读取内嵌 `#bidguard-report-snapshot` JSON，提供同步章节详情检索与内嵌 WebP 扫描件解析 |
| `frontend/src/App.tsx` | 全局布局状态编排（支持工作台三栏在线模式与离线双栏交互报告模式）、`EventSource` 实时事件订阅、全局快捷键（`⌘,`、`⌘\`） |
| `frontend/src/components/TopToolbar.tsx` | 顶栏：侧栏开关、项目/标段/离线报告徽章、居中实时遥测胶囊与模型用量浮层、一键「导出报告」HTML 下载、深浅色切换、设置入口 |
| `frontend/src/components/Sidebar.tsx` | 左栏：macOS Source List 风格项目列表、状态指示点、缓存占用展示与一键清理 |
| `frontend/src/components/MasterChatPane.tsx` | 中栏：双文档槽与 Master 会话流（支持在线指令交互与离线只读快照联跳、`导出报告` 一键导出） |
| `frontend/src/components/InspectorPane.tsx` | 右栏容器：`实况` / `报告` / `原文` 三段式 macOS 分段控制器（自适应在线分屏与离线全宽布局） |
| `frontend/src/components/LiveRunView.tsx` | 实况视图：可折叠形式预警卡片、五大维度分组清单、自定义 macOS 复选框（只读快照态自动锁定）与实时核查状态 |
| `frontend/src/components/ReportView.tsx` | 报告视图：封标结论与就绪度评分卡、四宫格统计、完整优先整改项、多维筛选胶囊与整改建议 |
| `frontend/src/components/EvidenceView.tsx` | 原文视图：条款对照卡（含视觉核验与整改建议）、章节快速跳转、原文段落、支持展开 `>35` 行长表格、扫描件画廊与全屏灯箱（支持 `Esc` 关闭） |
| `frontend/src/components/SettingsModal.tsx` | 设置面板：供应商密钥、`/models` API 实时模型列表拉取与可搜索选择器、四角色模型/并发/自动单价联动、底部外观三态切换器 |

---

## 三、数据存储、状态机与接口契约

### 3.1 本地运行时存储结构（`data/`，已排除在 Git 之外）
- `data/bidguard.db`：SQLite 数据库（启用 `WAL` 模式 + 线程可重入锁 `_DB_LOCK`），包含 5 张表：
  - `app_kv`：全局键值配置（`key='settings'` 存储供应商 API Key 与四角色路由 JSON）
  - `projects`：项目主表（名称、阶段、目标标段、双文档摘要 JSON、报告 JSON、遥测快照 JSON）
  - `checklist_items`：核查清单明细表（复合主键 `(project_id, item_id)`，每完成一项立即落盘防丢）
  - `messages`：Master 会话消息流（支持 `text`、`precheck_card`、`plan_card`、`report_ready`、`error`）
  - `token_ledger`：每次大模型调用的输入/输出 Token、耗时与成本流水表
- `data/uploads/`：流式接收的上传标书文件副本
- `data/ast_cache/`：解析后的 `DocumentAST` JSON 缓存（避免重复解析百兆文件）
- `data/media_cache/`：按需提取并压缩后的扫描件 `.jpg` 及 HTML 快照 `.webp` 缓存（支持在侧栏底部一键清理）
- `data/reports/`：导出的交互式静态 `.html` 报告（以及兼容接口 `.docx` / `.xlsx` 临时文件）

### 3.2 项目状态机（`stage`）
`idle`（就绪 / 待导入 / 待生成清单 / 已停止） → `parsing`（解析文档中） → `planning`（Master 拆解规划中，实时计时） → `awaiting_confirm`（待确认执行 / 待复检） → `inspecting`（并发核查中） → `assembling_report`（汇总报告中） → `completed`（已完成） / `error`（异常）。

### 3.3 核心 API 与 SSE 契约

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `GET / POST` | `/api/projects` | 获取项目列表 / 创建新项目 |
| `GET / DELETE` | `/api/projects/{id}` | 获取项目完整详情 / 中止在途任务并删除项目及关联缓存 |
| `GET` | `/api/workspace-samples` | 列出工作区根目录可直接零拷贝挂载的本地示例标书 |
| `POST` | `/api/projects/{id}/documents/upload` | `8MB` 分块流式上传 `.docx` / `.pdf`（双文档齐备后输出 0-Token 预检确认卡，不自动偷跑大模型） |
| `POST` | `/api/projects/{id}/documents/mount-local` | 直接挂载工作区本地大体积标书 |
| `PATCH` | `/api/projects/{id}/checklist/{item_id}` | 启用或跳过单条核查项（同步重算计划预估） |
| `POST` | `/api/projects/{id}/chat` | 向 Master Agent 发送自然语言指令 |
| `POST` | `/api/projects/{id}/plan` | 显式触发或按指定标段生成核查清单（支持 `async_run=true` 异步可取消执行） |
| `POST` | `/api/projects/{id}/run` | 启动后台并发核查（`recheck_only=true` 时仅复检问题项） |
| `POST` | `/api/projects/{id}/cancel` | 中止当前项目正在运行中的规划或核查后台任务 |
| `GET` | `/api/projects/{id}/events` | **SSE 实时流**：推送 `telemetry`、`item_updated`、`checklist_replaced`、`chat_message`、`report_ready`、`doc_mounted` |
| `GET` | `/api/projects/{id}/outline` | 获取响应文件目录大纲与固有红线扫描列表 |
| `GET` | `/api/projects/{id}/sections/{sec_id}` | 获取指定章节原文段落、表格与图片 ID |
| `GET` | `/api/projects/{id}/media/{media_id}` | 按需转码并返回章节内嵌扫描件 JPEG |
| `GET` | `/api/projects/{id}/export/html` | 导出真同源单文件交互式静态 HTML 报告（内嵌前端产物、全书章节表格与 WebP 扫描件） |
| `GET` | `/api/projects/{id}/export/docx` \| `/xlsx` | 导出 Word 核查报告 / Excel 整改销项表（向后兼容接口） |
| `GET / PUT` | `/api/settings` | 读取 / 保存供应商密钥与四角色路由配置 |
| `POST` | `/api/settings/models` | 调用供应商 OpenAI 兼容 `/models` 接口动态拉取可用模型清单、视觉能力标识与参考单价 |
| `POST` | `/api/settings/test` \| `/clear-cache` | 测试模型连通性 / 清理图片与导出缓存 |

---

## 四、本地启动、开发联调与验证规程

### 4.1 标准单体启动（推荐）
```bash
./run.sh
```
- 默认监听 `http://127.0.0.1:8000`（可通过 `PORT=8080 ./run.sh` 指定端口）。
- `run.sh` 会自动检测 `frontend/src`、`frontend/index.html`、`frontend/package.json` 是否比 `frontend/dist/index.html` 更新；若有前端改动会自动执行 `npm run build`，确保刷新浏览器即刻生效。

### 4.2 前端独立热更新联调（可选）
若需修改 UI 并实时 HMR 预览（`vite.config.ts` 已内置 `/api -> http://127.0.0.1:8000` 代理）：
```bash
# 终端 1：启动后端
.venv/bin/uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000

# 终端 2：启动前端 Vite 开发服
cd frontend && npm run dev
```
> 注意：联调结束后务必执行 `(cd frontend && npm run build)`，确保单体生产静态包同步更新。

### 4.3 自动化回归验证门禁
每次修改代码后必须顺序通过以下两条命令：
```bash
(cd frontend && npm run build)
.venv/bin/pytest -v
```

### 4.4 Windows 免 Python 独立打包与 GitHub 自动发版（`v0.5.0`）
1. **运行时双路径契约（`backend/config.py`）**：
   - **只读静态资产（`FRONTEND_DIST_DIR`）**：冻结态（`sys.frozen`）下解析自 `sys._MEIPASS/frontend/dist`；
   - **可写业务数据（`DATA_DIR`）**：优先使用可执行文件同级的 `data/`（便携绿色存储，升级保留 `data/` 即可保留全部项目与设置），若目录只读（如安装在 `Program Files`）自动回退至 `%LOCALAPPDATA%\BidGuard\data`（亦支持 `BIDGUARD_DATA_DIR` 覆盖）。
2. **本地 Windows 打包命令**：
   ```powershell
   pip install -e ".[dev,packaging]"
   pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1
   ```
   产出位于 `release/BidGuard-Windows-x64.zip`（与 `.sha256`），打包前会自动启动编译完成的 `dist/BidGuard/BidGuard.exe --self-test` 验证 SPA 托管、核心 API 及 Word/PDF/Excel 依赖库。
3. **GitHub Actions 自动发版（`.github/workflows/release.yml`）**：
   - 推送任意 `v*` 标签（如 `git tag -a v0.5.0 -m "Release v0.5.0" && git push origin v0.5.0`）、在 GitHub 网页端发布 Release，或手动触发 `workflow_dispatch`（填入 `release_tag`），均会在 `windows-latest` 上完成全量编译测试并将 `BidGuard-Windows-x64.zip`（含 SHA256）自动附加到对应的 GitHub Release。

---

## 五、安全与保密红线（严禁入库清单）

招投标文档通常包含商业机密、报价明细、身份证件、财务审计数据及客户合同，本地数据库亦包含大模型 API Key。提交 Git 前必须严格遵守：

1. **禁止入库文件类型**：`*.docx`、`*.doc`、`*.pdf`、`*.xlsx`、`*检查报告.html`、`*核查报告.html`、`~$*`、`data/`、`.env`、`.env.*`（`.env.example` 除外）、`frontend/dist/`、`frontend/node_modules/`。
2. **提交前强制安全自检命令**：
   ```bash
   git status
   git diff --cached --name-only
   ```
   确认暂存区中**绝无**任何标书原件、`bidguard.db` 或硬编码的 `sk-...` 密钥。

---

## 六、每次阶段执行后的强制交接规程（SOP）

项目根目录已同步配置 **[AGENTS.md](../AGENTS.md)** 守则。后续无论是人工开发还是 AI Agent 执行阶段任务，在任务收尾时**必须严格执行以下 5 步闭环**：

1. **编译与测试门禁**：运行 `(cd frontend && npm run build)` 与 `.venv/bin/pytest -v`，确保零报错通过。
2. **更新交接文档**：
   - 若新增/变更了架构模块、数据库字段、API 路由或运行依赖，同步更新本文档第 二～四 章及 `README.md`；
   - 在本文档 **第八章《里程碑交接台账》** 顶部或末尾追加本次迭代记录（包含日期、版本号、核心改动、修改文件清单、验证结果与遗留风险）。
3. **保密审计**：执行 `git status` 确认无涉密标书与运行时缓存混入。
4. **原子化 Git 提交**：遵循 Conventional Commits 规范（如 `feat(ui): ...`、`fix(parser): ...`、`docs(handover): ...`）提交到本地 `main` 分支。
5. **同步远端 GitHub**：执行 `git push` 推送至 GitHub 远端仓库，确保本地与远端 `HEAD` 一致。

---

## 七、GitHub 仓库首次绑定与日常同步指南

本项目已绑定远端仓库 **`https://github.com/artxom/BidCheck.git`**（默认通过 HTTPS 443 推送；如已配置 GitHub SSH 密钥并需切换为 SSH，可执行 `git remote set-url origin git@github.com:artxom/BidCheck.git`）。

### 7.1 发布新版本并触发 Windows 自动打包（Releases）

每当需要发布新版本（生成免 Python 安装的 `BidGuard-Windows-x64.zip` 下载包）时，只需在 `main` 分支创建并推送语义化版本标签：
```bash
git tag -a v0.5.1 -m "Release v0.5.1"
git push origin v0.5.1
```
或在 GitHub 仓库主页 **Releases -> Draft a new release** 直接创建标签并点击 **Publish release**，GitHub Actions 将在约 3–5 分钟内自动将 `BidGuard-Windows-x64.zip` 与校验文件上传至该 Release。

### 7.2 后续每次阶段迭代后的日常同步命令

首次执行过 `git push -u origin main` 绑定上游后，未来每次阶段任务完成并由 Agent 或您提交本地 Commit 后，只需一行命令即可同步至 GitHub：

```bash
git push
```

查看本地与 GitHub 远端同步状态：
```bash
git status -sb
git log --oneline -n 5
```

### 7.3 常见推送问题速查
- **HTTPS 提示输入密码失败**：GitHub 已停用账号登录密码认证，需在 `GitHub Settings -> Developer settings -> Personal access tokens (Tokens classic / Fine-grained)` 生成具备 `repo`（或 `Contents: Read and write`）权限的 Token 作为密码输入；或改用 `gh auth login`（GitHub CLI）/ SSH 密钥。
- **修改已绑定的远端地址**（如从 HTTPS 切换为 SSH）：
  ```bash
  git remote set-url origin git@github.com:您的用户名/仓库名.git
  ```
- **误将敏感文件加入暂存区的紧急撤销**：
  ```bash
  git reset HEAD <文件名>
  ```

---

## 八、里程碑交接台账（Milestone Handover Log）

### Milestone 6 — `v0.6.0`（2026-11-16）
- **阶段目标**：将报告导出升级为与工作台像素级同源的**单文件静态交互式 HTML 报告**，使报告审阅者双击 `.html` 文件即可在浏览器离线完整交互查看报告结论、实况清单、全部章节原文、长表格及扫描件大图。
- **核心变更内容**：
  1. **真同源 React + Tailwind v4 静态快照架构（`frontend/vite.config.ts` / `frontend/src/snapshot.ts` / `frontend/src/api.ts` / `frontend/src/App.tsx`）**：配置 Vite 单 CSS/单 JS 打包（`cssCodeSplit: false`、`inlineDynamicImports: true`）；新增 `OfflineReportSnapshot` 契约与 `snapshot.ts` 离线适配器，离线打开 HTML 时自动读取内嵌 `#bidguard-report-snapshot` JSON，零网络请求与零 SSE 连接同步渲染只读交互态工作台。
  2. **全链路交互升级与导出入口收敛（`TopToolbar.tsx` / `MasterChatPane.tsx` / `InspectorPane.tsx` / `LiveRunView.tsx` / `ReportView.tsx` / `EvidenceView.tsx`）**：将工作台顶栏与会话报告卡的 Word/Excel 按钮统一收敛为一键 **`导出报告`** 按钮（`Blob` 下载含加载态）；离线报告保留 Activity Capsule 用量浮层、浅色/深色切换、`⌘\` 面板折叠（`< 860px` 抽屉化）、`实况`/`报告`/`原文` 三段联动；`ReportView` 完整展示全部 `priority_actions`，`EvidenceView` 补充展示 `vision_note` 与 `remediation` 并支持 `>35` 行长表格一键展开/收起及全屏灯箱 `Esc` 关闭。
  3. **单文件 HTML 导出引擎与并发 WebP 压缩（`backend/exporters/html_exporter.py` / `backend/routers/reports.py`）**：新增 `GET /api/projects/{id}/export/html`；按 `source_key` 去重读取响应文件全量内嵌图片（支持 `.docx`/`.pdf` 与已缓存 `.jpg` 兜底），通过 `ThreadPoolExecutor` 并发合成白底并压缩为 `max_side=1000` WebP 缓存于 `MEDIA_CACHE_DIR`；剔除 `source_path` 本地绝对路径并对 JSON/CSS/JS 做防注入转义（保留 `/export/docx` 与 `/export/xlsx` 路由向后兼容）。
  4. **涉密防误提交与版本号更新（`.gitignore` / `backend/config.py` / `backend/main.py`）**：将 `*检查报告.html` 与 `*核查报告.html` 纳入 `.gitignore`，升级 `APP_VERSION` 至 `0.6.0`。
- **涉及主要文件**：
  - 新增：`backend/exporters/html_exporter.py`、`frontend/src/snapshot.ts`
  - 修改：`backend/config.py`、`backend/main.py`、`backend/routers/reports.py`、`frontend/vite.config.ts`、`frontend/src/types.ts`、`frontend/src/api.ts`、`frontend/src/App.tsx`、`frontend/src/components/TopToolbar.tsx`、`frontend/src/components/MasterChatPane.tsx`、`frontend/src/components/InspectorPane.tsx`、`frontend/src/components/LiveRunView.tsx`、`frontend/src/components/ReportView.tsx`、`frontend/src/components/EvidenceView.tsx`、`.gitignore`、`tests/test_ui_and_handover.py`、`tests/test_engine.py`、`README.md`、`docs/HANDOVER.md`
- **验证记录**：
  - `(cd frontend && npm run build)` 类型检查与单文件资产打包零报错通过（CSS `57.24 kB` / JS `323.84 kB`）
  - `.venv/bin/pytest -v` 11 项全量自动化测试通过（含合成 `.docx` XSS 转义、`source_path` 脱敏、45 行表格、RGBA->WebP 转码及真实样本全链路 HTML 导出测试）
  - 真实 636 页 / 488 图样本（`proj_167124d0da`）冷导出耗时 `2.49s`、缓存复用 `0.11s`，产出单文件 `22.87 MB`
  - Headless Microsoft Edge CDP 实测 `file://` 离线运行及 `1440×900` / `1024×768` / `390×844` 三视口零横向溢出、0 JS 异常、0 网络外联、图片全加载、572 行表格展开与灯箱 `Esc` 关闭全部通过；重启本地 `127.0.0.1:8000` 验证在线界面一键导出 `200 OK`
- **已知边界与下一阶段建议**：
  - 静态 HTML 报告内嵌全书文本与 WebP 压缩图，600+ 页标书导出包约 `20–25 MB`，支持任意现代浏览器离线秒开；`/export/docx` 与 `/export/xlsx` 后端接口继续保留以供脚本或兼容调用。

---

### Milestone 5 — `v0.5.0`（2026-11-16）
- **阶段目标**：补齐独立免 Python 的 Windows 桌面可执行打包能力、建立 GitHub Actions 自动发版 Release 流水线（产出 `BidGuard-Windows-x64.zip`），并完成 GitHub 远端库（`artxom/BidCheck`）起始版本上传。
- **核心变更内容**：
  1. **冻结运行时适配（`backend/config.py` / `backend/main.py` / `backend/exporters/docx_exporter.py`）**：新增 `resolve_runtime_paths`，自动识别 PyInstaller `_MEIPASS` 只读前端资产目录与可执行文件同级便携 `data/` 目录（含只读目录向 `%LOCALAPPDATA%\BidGuard\data` 安全回退）；修正 SPA `is_relative_to` 路径校检与 Windows Word 导出默认微软雅黑字体；`/api/health` 新增 `app` 与 `version` 字段。
  2. **独立桌面启动器与打包工程（`launcher.py` / `packaging/` / `scripts/build_windows.ps1`）**：实现无控制台日志兜底重定向、端口自动探测、Edge `--app=` 独立应用窗打开（含默认浏览器降级）、紧凑 `tkinter` 托盘控制窗及 `--self-test` 冒烟模式；完成多分辨率 `.ico` 图标生成脚本、PyInstaller `--onedir` `.spec` 与一键打 zip + SHA256 的 PowerShell 脚本（禁止将运行前测试产生的 `data/` 打入发布包）。
  3. **GitHub Actions 自动发版（`.github/workflows/release.yml`）**：监听 `v*` 标签推送、`release.published` 及 `workflow_dispatch`，在 `windows-latest` 上自动执行前端构建、`pytest` 全量门禁、PyInstaller 打包、`BidGuard.exe --self-test` 实跑校验，并通过 `softprops/action-gh-release@v2` 将 `BidGuard-Windows-x64.zip` 上传至 GitHub Releases。
  4. **CI 兼容与工程修复（`pyproject.toml` / `.gitignore` / `tests/`）**：补齐 `[build-system]`、`backend*` 包发现声明、显式 `httpx` / `certifi` 与 `packaging` 依赖；修复 `tests/test_ui_and_handover.py` 误引未声明的 `httpx2` 并新增冻结路径、图标生成、`launcher.py --self-test`、无本地样本 CI 合成 `.docx` 解析导出与发版工作流结构验证。
- **涉及主要文件**：
  - 新增：`launcher.py`、`packaging/generate_icon.py`、`packaging/bidguard.spec`、`scripts/build_windows.ps1`、`.github/workflows/release.yml`
  - 修改：`pyproject.toml`、`.gitignore`、`backend/config.py`、`backend/main.py`、`backend/exporters/docx_exporter.py`、`tests/test_ui_and_handover.py`、`README.md`、`docs/HANDOVER.md`
- **验证记录**：
  - `(cd frontend && npm run build)` 类型检查与 Vite 生产构建零错误通过
  - `.venv/bin/pytest -v` 10 项全量自动化测试通过（含 `launcher.py --self-test` 与合成 `.docx`/`.xlsx` 导出测试）
- **已知边界与下一阶段建议**：
  - Windows 安装包未做商业 Authenticode 代码签名，首次双击运行若遇 Windows Defender SmartScreen 蓝屏提示，点击「更多信息 -> 仍要运行」即可；macOS 本机无法交叉编译 Windows PE 二进制，实际 `BidGuard.exe` 与 `BidGuard-Windows-x64.zip` 由 GitHub Actions `windows-latest` 云端原生编译与冒烟校验生成。

---

### Milestone 4 — `v0.4.0`（2026-11-16）
- **阶段目标**：将双文件上传后的自动规划重构为 0-Token 预检确认闭环，解决推理模型（`deepseek-v4-pro` / `deepseek-flash`）默认思考链耗尽 `max_tokens` 导致的空 JSON 截断与同参盲目重试问题，并修复招标摘要合同泄漏、公共表格误删及目录截断缺陷。
- **核心变更内容**：
  1. **0-Token 上传预检确认与任务可取消闭环**：移除 `backend/routers/projects.py` 上传后自动启动大模型的偷跑逻辑，改为输出 `precheck_card`（展示页数、标段选择器、18 处本地形式预警及预计输入 Token），由用户显式点击「生成检查计划」后启动；新增 `POST /api/projects/{id}/cancel` 及顶栏/底部「停止」控制、规划阶段每秒耗时心跳与 `/chat`、`/plan` 异常防卡死保护。
  2. **推理模型防截断适配与网关止血**：在 `backend/llm/gateway.py` 缓存 `/models` 能力元数据，为支持 `effort` 的模型自动协商 `reasoning_effort="low"` 与 `response_format={"type": "json_object"}`（遇 HTTP 400 自动零损耗剥离降级），将各角色 `max_tokens` 提升至 `16384 / 4096 / 2048 / 6144`，关闭 SDK 隐式重试；遇到 `finish_reason="length"` 截断立即抛出 `NonRetryableLLMError` 并诊断思考 Token 消耗，严禁同参重试；每次调用记账后立即推送 SSE 遥测并修正单次耗时计时器；升级 `test_connection` 防止推理模型 `max_tokens=16` 空回复假阳性。
  3. **章节层级状态机与全书紧凑目录修复**：新增 `CURRENT_AST_VERSION = 2`（自动刷新旧 AST 缓存）；拆分 `CN_CHAPTER_RE` 与 `CN_APPENDIX_RE` 并加入章级归属保护（修复第五章合同附件越权弹出及第四章 `附件：身份证...` 污染面包屑，并放宽 `CN_H2_RE` 冒号结尾标题识别），使 `build_tender_digest` 彻底剔除第五章合同样板并完整保留第三/四章非功能需求；`build_response_outline_summary` 默认输出全书紧凑骨架目录（~3.8k 字符完整覆盖 `P1–P636`）。
  4. **严格遵守用户单价手工维护要求**：保留既有 `MODEL_PRICING_RULES` 与缓存折扣系数未做改动。
- **涉及主要文件**：
  - 后端：`backend/schemas.py`、`backend/parsers/models.py`、`backend/parsers/docx_parser.py`、`backend/parsers/pdf_parser.py`、`backend/parsers/indexer.py`、`backend/llm/gateway.py`、`backend/agents/master_agent.py`、`backend/agents/worker_engine.py`、`backend/agents/report_agent.py`、`backend/routers/projects.py`、`backend/routers/chat_stream.py`
  - 前端：`frontend/src/types.ts`、`frontend/src/api.ts`、`frontend/src/App.tsx`、`frontend/src/components/TopToolbar.tsx`、`frontend/src/components/MasterChatPane.tsx`
  - 文档与测试：`docs/HANDOVER.md`、`tests/test_ui_and_handover.py`
- **验证记录**：
  - `(cd frontend && npm run build)` 类型检查与 Vite 生产构建零报错通过
  - `.venv/bin/pytest -v` 9 项全量自动化测试通过（含 0-Token 预检验证、第五章剔除与非功能需求完整保留测试、`finish_reason="length"` 截断零重试测试、HTTP 400 参数降级测试、`/cancel` 任务中止测试）
  - 重启本地 `127.0.0.1:8000` 服务并验证 `/api/health` 与最新静态资源包加载
- **已知边界与下一阶段建议**：
  - 当前 `deepseek-v4-pro` 等单价由用户在设置面板手工维护；若接入支持直返 `usage.cost` 的聚合网关可自动读取账单实扣金额。

---

### Milestone 3 — `v0.3.0`（2026-11-16）
- **阶段目标**：将设置面板的模型选择升级为通过供应商 `/models` API 动态拉取实时清单并自动联动单价，同时把执行前预估升级为基于真实文档检索分块与角色单价的精确测算，并加固缓存命中与直返费用计费精度。
- **核心变更内容**：
  1. **动态模型列表 API 接入**：在 `backend/llm/gateway.py` 新增 `LLMGateway.list_models`（5 分钟 TTL 内存缓存、自动剥离 Gemini `models/` 前缀、过滤 embedding/whisper 等非对话模型、解析 OpenRouter `pricing` 或内置参考单价目录 `MODEL_PRICING_RULES`、推断多模态 `VL` 视觉支持），并暴露 `POST /api/settings/models` 接口。
  2. **macOS 可搜索模型选择器与单价联动**：重构 `frontend/src/components/SettingsModal.tsx`，在「供应商」页提供基于实时 API 模型列表的下拉测试选择器与状态反馈；在「模型路由」页实现带搜索过滤、自适应上下防裁切弹向（第 3、4 角色向上展开）、`VL` 视觉置顶标记、自定义接入点兜底及选中模型自动回填输入/输出单价。
  3. **Token 与费用测算/计费精度升级**：在 `backend/schemas.py` 新增 `TelemetrySnapshot.estimated_plan_cost`；在 `backend/agents/master_agent.py` 实现 `_estimate_plan_metrics`，依据响应文件实际命中的候选章节字符数、扫描件图片数与四角色绑定单价计算执行前预估费用及耗时，并在 `TopToolbar` 用量浮层与规划卡片中展示；在 `LLMGateway.chat_json` 中新增 `cached_tokens` / `prompt_cache_hit_tokens` 缓存命中折扣与 `usage.cost` 网关实扣金额识别。
- **涉及主要文件**：
  - 后端：`backend/config.py`、`backend/schemas.py`、`backend/llm/gateway.py`、`backend/routers/settings.py`、`backend/routers/projects.py`、`backend/agents/master_agent.py`
  - 前端：`frontend/src/types.ts`、`frontend/src/api.ts`、`frontend/src/components/SettingsModal.tsx`、`frontend/src/components/TopToolbar.tsx`
  - 文档与测试：`docs/HANDOVER.md`、`tests/test_ui_and_handover.py`
- **验证记录**：
  - `(cd frontend && npm run build)` 类型检查与 Vite 生产编译零错误通过
  - `.venv/bin/pytest -v` 7 项全量自动化测试通过（新增动态模型拉取过滤/价格解析、分块费用预估、缓存命中计费测试）
  - 重启本地 `127.0.0.1:8000` 服务并验证 `/api/health`、`POST /api/settings/models` 契约与页面静态加载
- **已知边界与下一阶段建议**：
  - 国内部分中转网关或私有部署端点若不实现标准 `/models` 或不返回 `pricing` 字段，选择器会自动保留输入自定义模型 ID 能力，单价框支持用户按实际协议折扣微调。

---

### Milestone 2 — `v0.2.0`（2026-11-16）
- **阶段目标**：精简全站冗余提示文案，升级原生 macOS 视觉层次与操控质感，支持深色模式（Dark Mode），建立严格的工程交接文档体系与 GitHub 同步规程。
- **核心变更内容**：
  1. **深色模式与三态外观引擎**：新增 `frontend/src/theme.ts` 与 `frontend/index.html` 首屏防闪烁脚本，基于 Tailwind v4 `@custom-variant dark (&:where(.dark, .dark *))` 实现 `浅色 / 深色 / 自动跟随系统` 三态切换（支持顶栏一键切换与设置面板三态选择，自动持久化至 `localStorage` 并实时响应 macOS 系统外观变化）。
  2. **macOS 原生材质、防溢出与操控质感升级**：在 `frontend/src/index.css` 建立高饱和毛玻璃工具栏（`.macos-toolbar`）、对称居中遥测胶囊、渐变源列表侧栏（`.macos-sidebar`，窄窗口自动抽屉化防裁切）、微高光内描边卡片（`.macos-card`）、内凹槽控件（`.macos-well` / `.macos-capsule` / `.macos-segmented`）、原生上下双箭头下拉框（`.macos-select`，防止长章节名横向撑破原文检视器）、光泽按钮与浮层提示条；修复空会话区假滚动条、左侧文档槽样本浮层越界、历史规划卡主按钮竞争与设置四角色面板裁切问题。
  3. **全站克制化文案与后端鲁棒性加固**：全面剔除前端空状态、设置项说明、筛选器与后端 Master 规划卡/报告卡中的教学式冗长提示词；将五大检查维度统一精简为四字标签（`资格审查`、`商务资信`、`技术方案`、`采购需求`、`形式红线`）；修复全局红线检查项 `is_global_redline` 关键词匹配、异常失败项报告结论防误判硬锁及不存在项目的 `/chat`、`plan` 路由 `404` 边界处理。
  4. **工程化启动与交接门禁体系**：升级 `run.sh` 支持检测前端源码变更自动增量重编译；在 `.gitignore` 排除 `*.tsbuildinfo`；新增 `AGENTS.md`、`.env.example`、重写 `README.md`、新建 `docs/HANDOVER.md` 及全覆盖回归测试 `tests/test_ui_and_handover.py`。
- **涉及主要文件**：
  - 前端：`frontend/index.html`、`frontend/package.json`、`frontend/src/index.css`、`frontend/src/theme.ts`、`frontend/src/types.ts`、`frontend/src/api.ts`、`frontend/src/App.tsx`、`frontend/src/components/*.tsx`（全部 8 个组件）
  - 后端：`backend/main.py`、`backend/config.py`、`backend/schemas.py`、`backend/db.py`、`backend/llm/gateway.py`、`backend/llm/prompts.py`、`backend/routers/projects.py`、`backend/routers/chat_stream.py`、`backend/agents/*.py`
  - 工程与文档：`.gitignore`、`pyproject.toml`、`run.sh`、`.env.example`、`AGENTS.md`、`README.md`、`docs/HANDOVER.md`、`tests/test_ui_and_handover.py`
- **验证记录**：
  - `cd frontend && npm run build`（`tsc -b && vite build` 零错误通过，验证 `.macos-*` 与 `:where(.dark,.dark *)` 规则）
  - `.venv/bin/pytest -v` 全量通过（含百兆真实标书解析、导出、API 边界与全局红线核查测试）
  - 真实 Chromium (Microsoft Edge Headless CDP) 多分辨率（`1440×900` / `1024×768` / `900×700`）浅色与深色模式逐屏渲染截图与 DOM 几何零溢出实测通过
- **已知边界与下一阶段建议**：
  - 当前导出 Word/Excel 报告采用固定商务浅底打印配色（符合线下纸质审阅与打印习惯，不受网页深色模式影响）；
  - 后续迭代可按需增加「自定义核查规则模板保存」或「新旧两版响应文件差异对比视图」。

---

### Milestone 1 — `v0.1.0`（2026-11-16，Commits `cd404d5` ~ `61cccca`）
- **阶段目标**：完成标书自动检查工作台首版全栈核心能力交付。
- **核心变更内容**：
  1. `cd404d5`：工程初始化、`.gitignore` 涉密隔离、原生 OOXML（`.docx`）/ PyMuPDF（`.pdf`）流式解析器、目录 `PAGEREF` 页码锚定、6 类确定性红线扫描器与混合章节检索器。
  2. `9b8f916`：SQLite WAL 仓储、多供应商 OpenAI 兼容网关、四角色路由与并发信号量、Master / Worker / Vision / Report 多 Agent 协同内核与实时遥测总线。
  3. `4439cd6`：FastAPI REST + SSE 服务层与初版 macOS 三栏式 React 前端工作台。
  4. `61cccca`：Word（`.docx`）核查报告与 Excel（`.xlsx`）整改销项表导出器、`run.sh` 一键启动脚本及真实百兆标书样本端到端自动化测试。
