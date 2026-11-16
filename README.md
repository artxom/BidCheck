# 标书智检 (BidGuard)

面向中国大陆招投标场景的自动化响应完整性与形式红线核查工作台。采用 **Master Agent 全局主控 + 应用固有确定性模块 + 并发文本/视觉小模型 + Report Assembler 报告总装** 的多层架构，配备简洁克制的 macOS 三栏式 Web 界面。

## 快速启动

```bash
chmod +x run.sh
./run.sh
```

浏览器访问 `http://127.0.0.1:8000` 即可使用（快捷键 `⌘,` 打开模型 API 与四角色路由设置）。

## 核心架构模块

- `backend/parsers/`：原生 OOXML 流式解析器（`.docx`）与 PyMuPDF 解析器（`.pdf`），结合目录 `PAGEREF` 书签实现秒级百兆文档章节树拆解、页码区间锚定、`<a:blip>` 图片按需转码压缩及内置确定性红线扫描（封面留空、`待补充` 占位符、空单元格、防串标错名、签章落款位）。
- `backend/llm/`：基于官方 `AsyncOpenAI` 标准协议的多供应商网关（预设阿里云百炼/通义、DeepSeek、火山豆包、硅基流动、OpenAI、Gemini、OpenRouter 及自定义兼容网关），内置按角色并发信号量、Token/费用实时台账与滑动窗口 ETA 估算。
- `backend/agents/`：`Master Agent`（会话交互、目标标段识别、核查清单编排、增量复检）、`Worker Engine`（逐项 SQLite 断点持久化、文本核对与按需多模态证照验图）、`Report Assembler Agent`（风险评级与封标结论组装）。
- `backend/exporters/`：一键导出正式 Word 核查报告（`.docx`）与团队分工整改销项表（`.xlsx`）。
- `frontend/`：React + TypeScript + Tailwind 构建的 macOS 三栏工作台（编译后由 FastAPI 单进程统一托管）。

## 运行自动化测试

```bash
.venv/bin/pytest -v
```
