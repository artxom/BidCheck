# 标书智检 (BidGuard)

面向中国大陆政企招投标场景的响应完整性与形式红线自动核查工作台。采用 **Master Agent 全局主控 + 确定性红线扫描 + 并发文本/视觉核验 + 报告总装** 架构，配备原生 macOS 质感三栏工作台（支持浅色 / 深色 / 跟随系统外观）。

> 工程架构、接口契约、每次迭代交接规范与 GitHub 同步指南详见：**[docs/HANDOVER.md](docs/HANDOVER.md)**

---

## 核心特性

- **百兆标书秒级拆解**：原生流式解析 `.docx`（OOXML）与 `.pdf`（PyMuPDF），基于目录 `PAGEREF` 书签精准锚定章节页码区间，内嵌扫描件按需懒转码压缩，轻松承载 150MB+ / 600+ 页标书。
- **零 Token 固有红线预警**：内置封面留空、`（待补充）` 占位符、关键表空单元格、采购人抬头/标段防串标错名、空章节及落款签章位确定性扫描，并对大模型结果施加防漏判硬锁。
- **四角色模型路由与实时遥测**：支持阿里云百炼（通义千问）、DeepSeek、火山豆包、硅基流动、OpenAI、Gemini、OpenRouter 及任意 OpenAI 兼容网关；前台胶囊实时展示进度、并发数、Token 消耗、费用与动态 ETA。
- **macOS 原生克制体验**：三栏分屏（项目侧栏 · Master 会话 · 实况/报告/原文检视器），精简无冗余提示文案，支持浅色、深色与跟随系统自动切换。
- **双格式离线交付**：一键导出正式 Word 核查报告（`.docx`）与团队分工整改销项表（`.xlsx`）。

---

## 快速启动

### 方式一：Windows 免安装独立桌面版（推荐终端用户）

**无需安装 Python 或 Node.js**：
1. 在 GitHub 仓库右侧 **Releases** 页面下载最新压缩包 `BidGuard-Windows-x64.zip`；
2. 将压缩包完整解压至任意本地文件夹；
3. 双击运行 **`BidGuard.exe`**，系统会自动以独立应用窗口（或默认浏览器）启动工作台。

> 如需在本地 Windows 环境自行打包：`pwsh -NoProfile -ExecutionPolicy Bypass -File scripts/build_windows.ps1`，产物位于 `release/BidGuard-Windows-x64.zip`。每次推送 `v*` 标签（如 `git tag v0.5.0 && git push origin v0.5.0`）或在 GitHub 页面发布 Release 时，GitHub Actions 会自动编译测试并附带 `BidGuard-Windows-x64.zip` 发布至 Releases。

### 方式二：macOS / Linux 源码一键启动

环境要求：**macOS / Linux**，**Python ≥ 3.11**，**Node.js ≥ 20**。

```bash
chmod +x run.sh
./run.sh
```

启动后浏览器访问 `http://127.0.0.1:8000`（`run.sh` 会自动维护 `.venv` 并在前端源码变更时自动重新编译静态产物）。

### 常用快捷键

| 快捷键 | 功能 |
| :--- | :--- |
| `⌘ ,` (`Ctrl + ,`) | 打开设置（供应商 API Key / 四角色路由 / 外观切换） |
| `⌘ \` (`Ctrl + \`) | 展开 / 收起左侧项目栏 |
| `Esc` | 关闭设置面板或扫描件大图预览 |

---

## 目录结构

```text
.
├── launcher.py              # 独立桌面启动器（支持 Windows 无控制台适配、端口自适应与 --self-test）
├── backend/
│   ├── main.py              # FastAPI 单体入口与静态 SPA 托管
│   ├── config.py            # 源码/PyInstaller 冻结双模式路径解析、主流供应商预设与四角色定义
│   ├── schemas.py           # 全局 Pydantic 数据契约
│   ├── db.py                # SQLite (WAL) 仓储、断点持久化与 Token 台账
│   ├── parsers/             # OOXML (.docx) / PDF 解析器、确定性扫描与混合检索器
│   ├── llm/                 # OpenAI 兼容异步网关、角色并发信号量与 SSE 事件总线
│   ├── agents/              # Master 主控、并发 Worker 引擎、Report 组装 Agent
│   ├── exporters/           # Word 核查报告与 Excel 整改销项表生成器
│   └── routers/             # 项目/上传、会话/SSE、报告导出、系统设置 API
├── frontend/                # React 19 + TypeScript + Tailwind v4 macOS 工作台
├── packaging/               # Windows 多分辨率 .ico 图标生成与 PyInstaller 打包配置 (.spec)
├── scripts/
│   └── build_windows.ps1    # Windows 独立可执行程序与发布 Zip 一键构建脚本
├── .github/workflows/
│   └── release.yml          # GitHub Actions 自动构建与 Release 资产发布流水线
├── tests/                   # 端到端解析、多 Agent 编排、UI 产物、打包自检与文档门禁测试
├── docs/
│   └── HANDOVER.md          # 工程交接手册、迭代 SOP、GitHub 提交流程与版本台账
├── AGENTS.md                # 每次迭代强制交接与 GitHub 同步守则
├── .env.example             # 可选环境变量模板
└── run.sh                   # macOS / Linux 一键构建与启动脚本
```

---

## 验证与测试

```bash
# 1. 前端类型检查与生产构建
(cd frontend && npm run build)

# 2. 后端与全链路自动化测试
.venv/bin/pytest -v
```

---

## 安全与涉密防护说明

本项目 `.gitignore` 已默认拦截所有 `*.docx`、`*.doc`、`*.pdf`、`*.xlsx` 标书文件以及包含 API Key 与解析缓存的 `data/`、`.env` 目录。**严禁使用 `git add -f` 强行提交真实招标文件、投标响应文件或本地数据库。**

首次关联与同步至 GitHub 仓库请直接参阅 **[docs/HANDOVER.md § 七、GitHub 仓库首次绑定与日常同步指南](docs/HANDOVER.md#七github-仓库首次绑定与日常同步指南)**。
