"""Global configuration and mainstream LLM provider presets."""

from __future__ import annotations

from collections.abc import Mapping
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

USD_TO_CNY_RATE: float = 7.25

NON_CHAT_MODEL_RE = re.compile(
    r"(embedding|rerank|bge-|moderation|whisper|tts|cosyvoice|paraformer|sensevoice|dall-e|flux|stable-diffusion|wanx|cogview|sora)",
    re.IGNORECASE,
)

# Reference CNY prices per 1M tokens (input, output). Specific patterns must precede general ones.
MODEL_PRICING_RULES: list[tuple[re.Pattern[str], float, float]] = [
    (re.compile(r"qwen-vl-max", re.I), 3.0, 9.0),
    (re.compile(r"qwen-vl-plus", re.I), 1.5, 4.5),
    (re.compile(r"qwen2\.5-vl-72b", re.I), 4.13, 4.13),
    (re.compile(r"qwen-max", re.I), 2.4, 9.6),
    (re.compile(r"qwen-plus", re.I), 0.8, 2.0),
    (re.compile(r"qwen-turbo", re.I), 0.3, 0.6),
    (re.compile(r"qwen2\.5-32b", re.I), 1.26, 1.26),
    (re.compile(r"deepseek-(reasoner|r1)", re.I), 4.0, 16.0),
    (re.compile(r"deepseek-(chat|v3)", re.I), 2.0, 8.0),
    (re.compile(r"doubao.*vision", re.I), 3.0, 9.0),
    (re.compile(r"doubao.*lite", re.I), 0.3, 0.6),
    (re.compile(r"doubao.*pro", re.I), 0.8, 2.0),
    (re.compile(r"glm-4v", re.I), 4.0, 4.0),
    (re.compile(r"glm-4-flash", re.I), 0.1, 0.1),
    (re.compile(r"glm-4-plus", re.I), 5.0, 5.0),
    (re.compile(r"moonshot-v1", re.I), 12.0, 12.0),
    (re.compile(r"gpt-4\.1-mini", re.I), 2.9, 11.6),
    (re.compile(r"gpt-4\.1", re.I), 14.5, 58.0),
    (re.compile(r"gpt-4o-mini", re.I), 1.1, 4.4),
    (re.compile(r"gpt-4o", re.I), 18.0, 72.0),
    (re.compile(r"(o3-mini|o4-mini)", re.I), 8.0, 32.0),
    (re.compile(r"\bo3\b", re.I), 14.5, 58.0),
    (re.compile(r"\bo1\b", re.I), 108.0, 435.0),
    (re.compile(r"gemini-2\.5-pro", re.I), 9.0, 72.0),
    (re.compile(r"gemini-2\.5-flash", re.I), 1.1, 4.4),
    (re.compile(r"gemini-2\.0-flash", re.I), 0.75, 3.0),
    (re.compile(r"claude-opus-4", re.I), 108.0, 540.0),
    (re.compile(r"claude-(sonnet-4|3-7-sonnet|3-5-sonnet)", re.I), 21.6, 108.0),
    (re.compile(r"claude-3-5-haiku", re.I), 5.8, 29.0),
]


def lookup_model_pricing(model_id: str) -> tuple[float, float] | None:
    """Return reference (input_price_per_m, output_price_per_m) in CNY if matched, else None."""
    mid = (model_id or "").strip()
    if not mid:
        return None
    for pattern, in_price, out_price in MODEL_PRICING_RULES:
        if pattern.search(mid):
            return in_price, out_price
    return None


def infer_vision_capability(model_id: str, raw_item: dict[str, Any] | None = None) -> bool:
    """Detect whether a model supports image inputs from provider metadata or model ID conventions."""
    if raw_item and isinstance(raw_item, dict):
        arch = raw_item.get("architecture")
        if isinstance(arch, dict):
            modality = str(arch.get("modality", "")).lower()
            if "image" in modality:
                return True
            input_mods = arch.get("input_modalities")
            if isinstance(input_mods, list) and any("image" in str(m).lower() for m in input_mods):
                return True
        input_mods_top = raw_item.get("input_modalities")
        if isinstance(input_mods_top, list) and any("image" in str(m).lower() for m in input_mods_top):
            return True
        caps = raw_item.get("capabilities")
        if isinstance(caps, dict) and caps.get("vision") is True:
            return True

    mid = (model_id or "").lower()
    return any(
        tok in mid
        for tok in (
            "vl",
            "vision",
            "qvq",
            "glm-4v",
            "pixtral",
            "gpt-4o",
            "gpt-4.1",
            "gemini-",
            "claude-3",
            "claude-sonnet-4",
            "claude-opus-4",
        )
    )

def _is_dir_writable(path: Path) -> bool:
    """Return True if a directory can be written to (Windows-safe ACL check)."""
    if path.exists():
        try:
            with tempfile.NamedTemporaryFile(dir=path, prefix=".bidguard_wtest_", delete=True):
                return True
        except OSError:
            return False
    parent = path.parent
    return os.access(parent, os.W_OK) if parent.exists() else True


def resolve_runtime_paths(
    is_frozen: bool | None = None,
    meipass: str | Path | None = None,
    executable: str | Path | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Path]:
    """Resolve runtime resource and writable data directories for source or PyInstaller frozen execution."""
    frozen = bool(getattr(sys, "frozen", False)) if is_frozen is None else is_frozen
    env_map = os.environ if env is None else env
    repo_root = Path(__file__).resolve().parent.parent
    exe_dir = Path(executable or sys.executable).resolve().parent

    base_dir = exe_dir if frozen else repo_root
    bundle_dir = Path(meipass or getattr(sys, "_MEIPASS", base_dir)).resolve() if frozen else repo_root

    frontend_dist = bundle_dir / "frontend" / "dist"
    if not frontend_dist.exists() and (base_dir / "frontend" / "dist").exists():
        frontend_dist = base_dir / "frontend" / "dist"

    env_data_dir = (env_map.get("BIDGUARD_DATA_DIR") or "").strip()
    if env_data_dir:
        data_dir = Path(env_data_dir)
    elif frozen:
        candidate = base_dir / "data"
        if candidate.exists():
            writable = _is_dir_writable(candidate)
        else:
            writable = _is_dir_writable(base_dir)
        if writable:
            data_dir = candidate
        else:
            local_base = Path(env_map.get("LOCALAPPDATA") or Path.home())
            data_dir = local_base / "BidGuard" / "data"
    else:
        data_dir = base_dir / "data"

    return {
        "BUNDLE_DIR": bundle_dir,
        "BASE_DIR": base_dir,
        "DATA_DIR": data_dir,
        "DB_PATH": data_dir / "bidguard.db",
        "UPLOADS_DIR": data_dir / "uploads",
        "AST_CACHE_DIR": data_dir / "ast_cache",
        "MEDIA_CACHE_DIR": data_dir / "media_cache",
        "REPORTS_DIR": data_dir / "reports",
        "FRONTEND_DIST_DIR": frontend_dist,
    }


IS_FROZEN: bool = bool(getattr(sys, "frozen", False))
_PATHS = resolve_runtime_paths()
BUNDLE_DIR: Path = _PATHS["BUNDLE_DIR"]
BASE_DIR: Path = _PATHS["BASE_DIR"]
DATA_DIR: Path = _PATHS["DATA_DIR"]
DB_PATH: Path = _PATHS["DB_PATH"]
UPLOADS_DIR: Path = _PATHS["UPLOADS_DIR"]
AST_CACHE_DIR: Path = _PATHS["AST_CACHE_DIR"]
MEDIA_CACHE_DIR: Path = _PATHS["MEDIA_CACHE_DIR"]
REPORTS_DIR: Path = _PATHS["REPORTS_DIR"]
FRONTEND_DIST_DIR: Path = _PATHS["FRONTEND_DIST_DIR"]


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
        "name": "自定义兼容网关",
        "base_url": "http://localhost:8000/v1",
        "suggested_models": [],
        "currency": "CNY",
    },
]

ROLE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "role": "master",
        "label": "主控规划 (Master)",
        "desc": "对话与清单编排",
        "default_concurrency": 2,
    },
    {
        "role": "text_worker",
        "label": "文本核查 (Text)",
        "desc": "并发章节条款比对",
        "default_concurrency": 6,
    },
    {
        "role": "vision_worker",
        "label": "视觉验图 (Vision)",
        "desc": "证照与扫描件核验",
        "default_concurrency": 3,
    },
    {
        "role": "report_assembler",
        "label": "报告总装 (Report)",
        "desc": "风险评级与结论汇总",
        "default_concurrency": 2,
    },
]
