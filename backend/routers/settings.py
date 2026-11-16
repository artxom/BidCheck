"""Settings, LLM Provider Configuration, Connectivity Test, and Cache Management Routes."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.config import PROVIDER_PRESETS, ROLE_DEFINITIONS
from backend.db import clear_media_and_report_caches, get_settings, get_storage_stats, save_settings
from backend.llm.gateway import LLM_GATEWAY
from backend.schemas import AppSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ConnectionTestRequest(BaseModel):
    base_url: str
    api_key: str
    model: str


class FetchModelsRequest(BaseModel):
    provider_id: str | None = None
    base_url: str = ""
    api_key: str = ""
    force_refresh: bool = False


@router.get("")
async def read_settings() -> dict[str, Any]:
    return {
        "settings": get_settings().model_dump(),
        "presets": PROVIDER_PRESETS,
        "roles": ROLE_DEFINITIONS,
        "storage": get_storage_stats(),
    }


@router.put("")
async def update_settings(payload: AppSettings) -> dict[str, Any]:
    saved = save_settings(payload)
    return {"settings": saved.model_dump()}


@router.post("/models")
async def fetch_provider_models(req: FetchModelsRequest) -> dict[str, Any]:
    base_url = req.base_url.strip()
    api_key = req.api_key.strip()
    if req.provider_id and (not base_url or not api_key):
        cfg = get_settings()
        matched = next((p for p in cfg.providers if p.id == req.provider_id), None)
        if matched:
            if not base_url:
                base_url = matched.base_url.strip()
            if not api_key:
                api_key = matched.api_key.strip()

    if not base_url or not api_key:
        raise HTTPException(status_code=400, detail="请先配置 Base URL 与 API Key")

    try:
        models = await LLM_GATEWAY.list_models(base_url, api_key, force_refresh=req.force_refresh)
        return {"models": models, "count": len(models)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"获取模型列表失败：{str(exc)[:200]}") from exc


@router.post("/test")
async def test_provider_connection(req: ConnectionTestRequest) -> dict[str, Any]:
    if not req.api_key.strip() or not req.base_url.strip() or not req.model.strip():
        raise HTTPException(status_code=400, detail="请完整填写 Base URL、API Key 与模型名称")
    try:
        return await LLM_GATEWAY.test_connection(req.base_url, req.api_key, req.model)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"连接失败：{str(exc)[:200]}") from exc


@router.post("/clear-cache")
async def clear_caches() -> dict[str, Any]:
    res = clear_media_and_report_caches()
    return {**res, "storage": get_storage_stats()}
