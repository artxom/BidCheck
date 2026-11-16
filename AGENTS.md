# AGENTS.md — BidGuard 工程迭代与交接维护守则

本文件为所有开发会话与 AI Agent 的强制执行准则。详情与完整架构契约以 **[docs/HANDOVER.md](docs/HANDOVER.md)** 为唯一权威基准。

## 1. 核心产品与界面准则
- **单一主控入口**：所有用户意图表达、标段锁定、清单裁剪与复检指令均通过 **Master Agent** 完成。
- **实时可观测遥测**：前台顶部状态胶囊必须清晰呈现阶段进度、Token 消耗、模型并发与预估剩余时间（ETA）。
- **macOS 原生克制美学**：严格保持简洁干练的标签体系，禁止引入教学式冗长提示词；所有新增 UI 必须同时兼容 **浅色 / 深色 / 自动跟随系统** 外观，并确保窄窗口与浮层不溢出。

## 2. 每次执行完成后的强制交接闭环（Ironclad Handover SOP）
每次功能开发、重构或缺陷修复执行完毕后，**必须按顺序完成以下 5 步，缺一不可**：

1. **构建与自动化测试门禁**：
   ```bash
   (cd frontend && npm run build)
   .venv/bin/pytest -v
   ```
2. **同步更新交接文档**：
   - 更新 `docs/HANDOVER.md` 中对应的模块、接口或数据契约说明（如有变更）；
   - 在 `docs/HANDOVER.md` 第八章《里程碑交接台账》记录本次迭代的版本、改动摘要、涉及文件与验证结果。
3. **涉密安全自检**：执行 `git status` 与 `git diff --cached --name-only`，严禁将任何 `*.docx`、`*.pdf`、`*.xlsx` 标书原件、`data/` 数据库或真实 API Key 提交入库。
4. **原子化 Git 提交**：遵循 Conventional Commits 规范提交至 `main` 分支。
5. **同步 GitHub 远端仓库**：若已配置 `origin` 远端（`git remote -v`），立即执行 `git push` 保持本地与 GitHub 一致；若尚未绑定远端，向用户提示绑定与推送命令（见 `docs/HANDOVER.md` 第七章）。
