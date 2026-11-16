"""Master Agent Chat, Plan Trigger, Inspection Run Trigger, and SSE Telemetry Stream Routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend.agents.master_agent import (
    generate_inspection_plan,
    handle_user_chat,
    launch_background_inspection,
)
from backend.db import append_message, get_project
from backend.llm.gateway import EVENT_BUS

router = APIRouter(prefix="/api/projects/{project_id}", tags=["chat & stream"])


class ChatRequest(BaseModel):
    message: str


class PlanRequest(BaseModel):
    target_lot: str | None = None


class RunRequest(BaseModel):
    recheck_only: bool = False


@router.post("/chat")
async def api_send_chat(project_id: str, req: ChatRequest) -> dict[str, Any]:
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="消息不能为空")
    try:
        msg = await handle_user_chat(project_id, req.message)
        return {"message": msg.model_dump(), "project": get_project(project_id).model_dump()}  # type: ignore[union-attr]
    except Exception as exc:
        err_msg = append_message(
            project_id,
            "assistant",
            f"处理请求异常：`{str(exc)[:220]}`",
            msg_type="error",
        )
        await EVENT_BUS.emit(project_id, "chat_message", err_msg.model_dump())
        raise HTTPException(status_code=400, detail=str(exc)[:220]) from exc


@router.post("/plan")
async def api_trigger_plan(project_id: str, req: PlanRequest) -> dict[str, Any]:
    try:
        msg = await generate_inspection_plan(project_id, target_lot_override=req.target_lot)
        return {"message": msg.model_dump(), "project": get_project(project_id).model_dump()}  # type: ignore[union-attr]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)[:240]) from exc


@router.post("/run")
async def api_start_run(project_id: str, req: RunRequest) -> dict[str, Any]:
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    if not proj.checklist:
        raise HTTPException(status_code=400, detail="尚未生成检查计划清单")

    started = launch_background_inspection(project_id, recheck_only=req.recheck_only)
    if started:
        enabled_cnt = sum(1 for it in proj.checklist if it.enabled)
        note = (
            "已启动增量复检，正在核对未通过与待补充条目…"
            if req.recheck_only
            else f"已启动并发核查（共 `{enabled_cnt}` 项），正在逐章核对响应内容…"
        )
        msg = append_message(project_id, "assistant", note, msg_type="text")
        await EVENT_BUS.emit(project_id, "chat_message", msg.model_dump())
    return {"started": started}


@router.get("/events")
async def api_project_sse(project_id: str, request: Request) -> StreamingResponse:
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    queue = EVENT_BUS.subscribe(project_id)

    async def _event_generator():
        try:
            # Push initial snapshot immediately upon connection
            init_payload = json.dumps(proj.telemetry.model_dump(), ensure_ascii=False)
            yield f"event: telemetry\ndata: {init_payload}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=15.0)
                    ev_name = evt["event"]
                    ev_data = json.dumps(evt["data"], ensure_ascii=False)
                    yield f"event: {ev_name}\ndata: {ev_data}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            EVENT_BUS.unsubscribe(project_id, queue)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
