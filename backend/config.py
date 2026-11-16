"""Global configuration and mainstream LLM provider presets."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("BIDGUARD_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = DATA_DIR / "bidguard.db"
UPLOADS_DIR = DATA_DIR / "uploads"
AST_CACHE_DIR = DATA_DIR / "ast_cache"
MEDIA_CACHE_DIR = DATA_DIR / "media_cache"
REPORTS_DIR = DATA_DIR / "reports"
FRONTEND_DIST_DIR = BASE_DIR / "frontend" / "dist"


def ensure_data_dirs() -> None:
    for d in (DATA_DIR, UPLOADS_DIR, AST_CACHE_DIR, MEDIA_CACHE_DIR, REPORTS_DIR):
        d.mkdir(parents=True, exist_ok=True)


PROVIDER_PRESETS: list[dict[str, Any]] = [
    {
        "id": "dashscope",
        "name": "阿里云百炼 (通义千问)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "suggested_models": [
            {"id": "qwen-max", "label": "Qwen-Max (主控/报告)", "vision": False, "input_price": 2.4, "output_price": 9.6},
            {"id": "qwen-plus", "label": "Qwen-Plus (均衡主力)", "vision": False, "input_price": 0.8, "output_price": 2.0},
            {"id": "qwen-turbo", "label": "Qwen-Turbo (极速低价检查)", "vision": False, "input_price": 0.3, "output_price": 0.6},
            {"id": "qwen-vl-plus", "label": "Qwen-VL-Plus (证照视觉核验)", "vision": True, "input_price": 1.5, "output_price": 4.5},
        ],
        "currency": "CNY",
    },
    {
        "id": "deepseek",
        "name": "DeepSeek 官方",
        "base_url": "https://api.deepseek.com/v1",
        "suggested_models": [
            {"id": "deepseek-chat", "label": "DeepSeek-V3 (高性价比通用)", "vision": False, "input_price": 2.0, "output_price": 8.0},
            {"id": "deepseek-reasoner", "label": "DeepSeek-R1 (深度推理规划)", "vision": False, "input_price": 4.0, "output_price": 16.0},
        ],
        "currency": "CNY",
    },
    {
        "id": "volcengine",
        "name": "火山方舟 (豆包 Doubao)",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "suggested_models": [
            {"id": "doubao-1-5-pro-32k-250115", "label": "Doubao-1.5-Pro", "vision": False, "input_price": 0.8, "output_price": 2.0},
            {"id": "doubao-1-5-lite-32k-250115", "label": "Doubao-1.5-Lite (并发检查)", "vision": False, "input_price": 0.3, "output_price": 0.6},
            {"id": "doubao-1-5-vision-pro-32k-250115", "label": "Doubao-Vision-Pro (视觉)", "vision": True, "input_price": 3.0, "output_price": 9.0},
        ],
        "currency": "CNY",
    },
    {
        "id": "siliconflow",
        "name": "硅基流动 (SiliconFlow)",
        "base_url": "https://api.siliconflow.cn/v1",
        "suggested_models": [
            {"id": "deepseek-ai/DeepSeek-V3", "label": "DeepSeek-V3", "vision": False, "input_price": 2.0, "output_price": 8.0},
            {"id": "Qwen/Qwen2.5-32B-Instruct", "label": "Qwen2.5-32B (高速检查)", "vision": False, "input_price": 1.26, "output_price": 1.26},
            {"id": "Qwen/Qwen2.5-VL-72B-Instruct", "label": "Qwen2.5-VL-72B (视觉)", "vision": True, "input_price": 4.13, "output_price": 4.13},
        ],
        "currency": "CNY",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "suggested_models": [
            {"id": "gpt-4o", "label": "GPT-4o (全能多模态)", "vision": True, "input_price": 18.0, "output_price": 72.0},
            {"id": "gpt-4o-mini", "label": "GPT-4o-mini (极速多模态)", "vision": True, "input_price": 1.1, "output_price": 4.4},
        ],
        "currency": "CNY",
    },
    {
        "id": "gemini",
        "name": "Google Gemini (OpenAI 兼容)",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "suggested_models": [
            {"id": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "vision": True, "input_price": 9.0, "output_price": 72.0},
            {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash (高速多模态)", "vision": True, "input_price": 1.1, "output_price": 4.4},
        ],
        "currency": "CNY",
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "suggested_models": [
            {"id": "anthropic/claude-sonnet-4", "label": "Claude Sonnet 4", "vision": True, "input_price": 21.6, "output_price": 108.0},
            {"id": "google/gemini-2.5-flash", "label": "Gemini 2.5 Flash", "vision": True, "input_price": 1.1, "output_price": 4.4},
        ],
        "currency": "CNY",
    },
    {
        "id": "custom",
        "name": "自定义 OpenAI 兼容网关 (NewAPI / OneAPI / vLLM)",
        "base_url": "http://localhost:8000/v1",
        "suggested_models": [],
        "currency": "CNY",
    },
]

ROLE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "role": "master",
        "label": "Master 主控 Agent",
        "desc": "负责需求对话、标段识别与检查计划制定",
        "default_concurrency": 2,
    },
    {
        "role": "text_worker",
        "label": "文本并发检查模块",
        "desc": "负责高并发逐章节核对条款响应情况",
        "default_concurrency": 6,
    },
    {
        "role": "vision_worker",
        "label": "视觉图片核验模块",
        "desc": "按需核验证照、财报、身份证及业绩合同扫描件",
        "default_concurrency": 3,
    },
    {
        "role": "report_assembler",
        "label": "报告组装 Agent",
        "desc": "负责统计全局结果、评估封标风险并生成总结",
        "default_concurrency": 2,
    },
]
