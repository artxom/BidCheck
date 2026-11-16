# BidGuard（标书智检）工程交接与迭代维护手册

> **文档定位**：本文件为项目的**权威工程交接基准（Single Source of Truth）**。依据项目维护铁律，**每次阶段性开发或优化执行完毕后，必须通过全部自动化测试、同步更新本交接文档的架构说明与第八章《里程碑交接台账》，并提交同步至 GitHub 远端仓库。**

- **当前版本**：`v0.3.0`
- **主干分支**：`main`
- **技术栈**：Python 3.11+ / FastAPI / SQLite (WAL) / lxml / PyMuPDF / AsyncOpenAI + React 19 / TypeScript / Vite 6 / Tailwind CSS v4

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
│  │ • BM25+标题层级检索  │  │ • docx/xlsx 导出器   │  │ • 动态 ETA 估算器  │  │
│  └──────────┬───────────┘  └──────────┬───────────┘  └─────────┬──────────┘  │
│             └─────────────────────────┼────────────────────────┘             │
│                                       ▼                                      │
│               SQLite WAL (data/bidguard.db) + AST/JPEG 按需缓存              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 后端代码模块清单

| 路径 | 核心职责 |
| :--- | :--- |
| `backend/main.py` | FastAPI 生命周期初始化、CORS、挂载四大 API 路由及托管 `frontend/dist` 单页应用 |
| `backend/config.py` | 运行时目录定义、8 家主流模型供应商预设、参考单价目录（`MODEL_PRICING_RULES`）、视觉能力推断（`infer_vision_capability`）与四角色定义 |
| `backend/schemas.py` | Pydantic 核心契约（`AppSettings`、`ChecklistItem`、`TelemetrySnapshot` 含 `estimated_plan_cost`、`InspectionReport`、`ProjectDetail`） |
| `backend/db.py` | SQLite WAL 连接池锁管理、项目 CRUD、检查项断点持久化、会话历史与 `token_ledger` 聚合统计 |
| `backend/parsers/docx_parser.py` | 原生 OOXML 流式解析段落/表格/`<a:blip>` 图片引用，结合目录 `PAGEREF` 书签映射精准页码，支持 `.tiff`/`.png` 懒转码压缩 JPEG |
| `backend/parsers/pdf_parser.py` | 基于 PyMuPDF (`fitz`) 的 PDF 书签大纲/字号启发式分章、文本表格提取与内嵌图按需转码 |
| `backend/parsers/indexer.py` | 封面/标段元数据提取、6 类零 Token 确定性红线扫描器、`SectionRetriever` 混合检索器、AST 磁盘缓存 |
| `backend/llm/gateway.py` | `LLMGateway`（四角色路由、`/models` 动态模型拉取与 5 分钟缓存、`cached_tokens`/`usage.cost` 精准计费、信号量限流、容错 JSON 解析）与 `ProjectEventBus` |
| `backend/llm/prompts.py` | 针对中国大陆招投标定制的四角色 System Prompts（规划、文本核查、视觉验图、报告总装、会话控制） |
| `backend/agents/master_agent.py` | 双文档规划拆解、基于真实检索章节字数与角色单价的 `_estimate_plan_metrics` 预估、强制注入全局红线核查项、自然语言意图分发 |
| `backend/agents/worker_engine.py` | 异步并发逐项核查、确定性致命占位符强制降级硬锁（防误判 `passed`）、按需多模态验图 |
| `backend/agents/report_agent.py` | 全局响应统计、就绪度评分计算、封标风险结论汇编（含无 API 异常时的确定性兜底报告） |
| `backend/exporters/docx_exporter.py` | 使用 `python-docx` 生成正式排版 Word 核查报告（总体结论、优先整改、固有预警、逐项明细表） |
| `backend/exporters/xlsx_exporter.py` | 使用 `openpyxl` 生成双 Sheet Excel 整改销项表（问题项自动置顶、状态着色、责任人认领列与自动筛选） |
| `backend/routers/*.py` | `projects.py`（8MB 流式上传、样本挂载、章节/图片预览）、`chat_stream.py`（对话、运行、SSE）、`reports.py`（导出）、`settings.py`（配置与连通性测试） |

### 2.3 前端代码模块清单

| 路径 | 核心职责 |
| :--- | :--- |
| `frontend/index.html` | 页面骨架与首屏防闪烁（FOUC-free）深浅色模式同步脚本 |
| `frontend/src/theme.ts` | `useTheme` 状态钩子：管理 `light` / `dark` / `system` 三态、`localStorage` 持久化与系统 `prefers-color-scheme` 实时监听 |
| `frontend/src/index.css` | Tailwind v4 `@custom-variant dark` 类驱动声明及 macOS 材质样式体系（`.macos-toolbar`、`.macos-sidebar`、`.macos-card`、`.macos-popover`、`.macos-segmented` 等） |
| `frontend/src/App.tsx` | 全局三栏布局状态编排、每个活跃项目的 `EventSource` 实时事件订阅、全局快捷键（`⌘,`、`⌘\`） |
| `frontend/src/components/TopToolbar.tsx` | 顶栏：侧栏开关、项目与标段徽章、居中实时遥测胶囊与模型用量/计划预估浮层、导出菜单、深浅色一键切换、设置入口 |
| `frontend/src/components/Sidebar.tsx` | 左栏：macOS Source List 风格项目列表、状态指示点、缓存占用展示与一键清理 |
| `frontend/src/components/MasterChatPane.tsx` | 中栏：双文档拖拽/本地样本挂载槽、Master 极简会话流、内联操作卡片与指令输入栏 |
| `frontend/src/components/InspectorPane.tsx` | 右栏容器：`实况` / `报告` / `原文` 三段式 macOS 分段控制器 |
| `frontend/src/components/LiveRunView.tsx` | 实况视图：可折叠形式预警卡片、五大维度分组清单、自定义 macOS 复选框与实时核查状态 |
| `frontend/src/components/ReportView.tsx` | 报告视图：封标结论与就绪度评分卡、四宫格统计、优先整改项、多维筛选胶囊与整改建议 |
| `frontend/src/components/EvidenceView.tsx` | 原文视图：条款对照卡、章节快速跳转、原文段落/空单元格高亮表格、扫描件画廊与全屏灯箱（支持 `Esc` 关闭） |
| `frontend/src/components/SettingsModal.tsx` | 设置面板：供应商密钥、`/models` API 实时模型列表拉取与可搜索选择器、四角色模型/并发/自动单价联动、底部外观三态切换器 |

---

## 三、数据存储、状态机与接口契约

### 3.1 本地运行时存储结构（`data/`，已排除在 Git 之外）
- `data/bidguard.db`：SQLite 数据库（启用 `WAL` 模式 + 线程可重入锁 `_DB_LOCK`），包含 5 张表：
  - `app_kv`：全局键值配置（`key='settings'` 存储供应商 API Key 与四角色路由 JSON）
  - `projects`：项目主表（名称、阶段、目标标段、双文档摘要 JSON、报告 JSON、遥测快照 JSON）
  - `checklist_items`：核查清单明细表（复合主键 `(project_id, item_id)`，每完成一项立即落盘防丢）
  - `messages`：Master 会话消息流（支持 `text`、`plan_card`、`report_ready`、`error`）
  - `token_ledger`：每次大模型调用的输入/输出 Token、耗时与成本流水表
- `data/uploads/`：流式接收的上传标书文件副本
- `data/ast_cache/`：解析后的 `DocumentAST` JSON 缓存（避免重复解析百兆文件）
- `data/media_cache/`：按需提取并压缩后的扫描件 `.jpg` 缓存（支持在侧栏底部一键清理）
- `data/reports/`：导出的 `.docx` 与 `.xlsx` 临时报告文件

### 3.2 项目状态机（`stage`）
`idle`（就绪/待导入） → `parsing`（解析文档中） → `planning`（Master 拆解规划中） → `awaiting_confirm`（待确认执行/待复检） → `inspecting`（并发核查中） → `assembling_report`（汇总报告中） → `completed`（已完成） / `error`（异常）。

### 3.3 核心 API 与 SSE 契约

| 方法 | 路径 | 说明 |
| :--- | :--- | :--- |
| `GET / POST` | `/api/projects` | 获取项目列表 / 创建新项目 |
| `GET / DELETE` | `/api/projects/{id}` | 获取项目完整详情 / 删除项目及关联缓存 |
| `GET` | `/api/workspace-samples` | 列出工作区根目录可直接零拷贝挂载的本地示例标书 |
| `POST` | `/api/projects/{id}/documents/upload` | `8MB` 分块流式上传 `.docx` / `.pdf`（双文档齐备后自动异步触发规划） |
| `POST` | `/api/projects/{id}/documents/mount-local` | 直接挂载工作区本地大体积标书 |
| `PATCH` | `/api/projects/{id}/checklist/{item_id}` | 启用或跳过单条核查项 |
| `POST` | `/api/projects/{id}/chat` | 向 Master Agent 发送自然语言指令 |
| `POST` | `/api/projects/{id}/plan` | 显式触发或按指定标段重生成核查清单 |
| `POST` | `/api/projects/{id}/run` | 启动后台并发核查（`recheck_only=true` 时仅复检问题项） |
| `GET` | `/api/projects/{id}/events` | **SSE 实时流**：推送 `telemetry`、`item_updated`、`checklist_replaced`、`chat_message`、`report_ready`、`doc_mounted` |
| `GET` | `/api/projects/{id}/outline` | 获取响应文件目录大纲与固有红线扫描列表 |
| `GET` | `/api/projects/{id}/sections/{sec_id}` | 获取指定章节原文段落、表格与图片 ID |
| `GET` | `/api/projects/{id}/media/{media_id}` | 按需转码并返回章节内嵌扫描件 JPEG |
| `GET` | `/api/projects/{id}/export/docx` \| `/xlsx` | 导出 Word 核查报告 / Excel 整改销项表 |
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

---

## 五、安全与保密红线（严禁入库清单）

招投标文档通常包含商业机密、报价明细、身份证件、财务审计数据及客户合同，本地数据库亦包含大模型 API Key。提交 Git 前必须严格遵守：

1. **禁止入库文件类型**：`*.docx`、`*.doc`、`*.pdf`、`*.xlsx`、`~$*`、`data/`、`.env`、`.env.*`（`.env.example` 除外）、`frontend/dist/`、`frontend/node_modules/`。
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

当前本地仓库已在 `main` 分支完成所有里程碑提交。由于您已准备好自己的 GitHub 仓库，请按以下指引完成绑定与推送：

### 7.1 首次关联您的 GitHub 远端仓库

先在终端进入项目根目录：
```bash
cd /Users/artxom/code/标书检查工具
```

在您的 GitHub 仓库页面复制仓库地址（推荐使用 **SSH** 如 `git@github.com:您的用户名/仓库名.git`，或 **HTTPS** 如 `https://github.com/您的用户名/仓库名.git`），执行：

```bash
# 1. 绑定远端仓库地址（请将下方 URL 替换为您的真实 GitHub 仓库地址）
git remote add origin <您的_GitHub_仓库地址>

# 2. 确认远端地址绑定无误
git remote -v
```

#### 情况 A：您的 GitHub 仓库是新建的空仓库（创建时未勾选 README / .gitignore / License）
直接推送并绑定上游分支即可：
```bash
git branch -M main
git push -u origin main
```

#### 情况 B：您的 GitHub 仓库创建时已自动生成了初始文件（如 README.md 或 LICENSE）
若直接 `git push` 提示 `rejected (fetch first)`，请先拉取合并远端初始提交（保留本地我们已撰写的完整 `README.md` 与 `.gitignore`），再推送：
```bash
git fetch origin
git merge origin/main --allow-unrelated-histories -X ours -m "chore: merge initial GitHub repository history"
git push -u origin main
```

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
