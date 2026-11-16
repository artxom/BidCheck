"""Project CRUD, Streaming Large File Upload, Local Sample Mount, Section Evidence & Media Preview Routes."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.agents.master_agent import (
    _estimate_plan_metrics,
    _load_response_ast_if_cached,
    cancel_project_task,
    emit_document_precheck,
)
from backend.config import BASE_DIR, UPLOADS_DIR, ensure_data_dirs
from backend.db import (
    append_message,
    create_project,
    delete_project,
    get_project,
    list_projects,
    update_project_fields,
    upsert_checklist_item,
)
from backend.llm.gateway import EVENT_BUS
from backend.parsers.indexer import (
    extract_media_jpeg,
    parse_and_cache_document,
)
from backend.parsers.models import DocumentAST
from backend.schemas import DocumentSummary

router = APIRouter(prefix="/api", tags=["projects"])


class CreateProjectReq(BaseModel):
    name: str = "新建项目"


class MountLocalDocReq(BaseModel):
    doc_role: Literal["tender", "response"]
    filename: str


class ToggleItemReq(BaseModel):
    enabled: bool


def _to_doc_summary(ast: DocumentAST) -> DocumentSummary:
    meta = dict(ast.metadata)
    meta["source_path"] = ast.source_path
    return DocumentSummary(
        doc_id=ast.doc_id,
        filename=ast.filename,
        file_type=ast.file_type,
        doc_role=ast.doc_role,
        file_size_bytes=ast.file_size_bytes,
        total_pages=ast.total_pages,
        total_chars=ast.total_chars,
        total_tables=ast.total_tables,
        total_images=ast.total_images,
        detected_lots=ast.detected_lots,
        metadata=meta,
        deterministic_count=len(ast.deterministic_findings),
    )


async def _finalize_mounted_doc(project_id: str, doc_role: str, file_path: Path) -> dict[str, Any]:
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    await EVENT_BUS.sync_and_broadcast_telemetry(
        project_id,
        stage="parsing",
        stage_label=f"解析{'招标' if doc_role == 'tender' else '响应'}文档",
    )

    doc_id = f"{project_id}_{doc_role}_{uuid.uuid4().hex[:6]}"
    tender_ast: DocumentAST | None = None
    if doc_role == "response" and proj.tender_doc:
        t_path = proj.tender_doc.metadata.get("source_path", "")
        if t_path and Path(t_path).exists():
            tender_ast = await asyncio.to_thread(
                parse_and_cache_document, t_path, "tender", proj.tender_doc.doc_id
            )

    ast = await asyncio.to_thread(
        parse_and_cache_document,
        file_path,
        doc_role,
        doc_id,
        tender_ast,
        True,
    )
    summary = _to_doc_summary(ast)

    # If tender was uploaded AFTER response, re-run deterministic cross-checks on response!
    r_ast: DocumentAST | None = None
    updated_resp_summary: DocumentSummary | None = None
    if doc_role == "tender" and proj.response_doc:
        r_path = proj.response_doc.metadata.get("source_path", "")
        if r_path and Path(r_path).exists():
            r_ast = await asyncio.to_thread(
                parse_and_cache_document, r_path, "response", proj.response_doc.doc_id, ast, True
            )
            updated_resp_summary = _to_doc_summary(r_ast)

    fields_to_save: dict[str, Any] = {}
    if doc_role == "tender":
        fields_to_save["tender_doc_json"] = summary.model_dump_json()
        if ast.metadata.get("project_name") and proj.name.startswith("新建"):
            fields_to_save["name"] = ast.metadata["project_name"][:60]
        if updated_resp_summary:
            fields_to_save["response_doc_json"] = updated_resp_summary.model_dump_json()
    else:
        fields_to_save["response_doc_json"] = summary.model_dump_json()
        if ast.metadata.get("target_lot"):
            fields_to_save["target_lot"] = ast.metadata["target_lot"]

    update_project_fields(project_id, **fields_to_save)
    await EVENT_BUS.emit(project_id, "doc_mounted", {"doc_role": doc_role, "summary": summary.model_dump()})

    refreshed = get_project(project_id)
    assert refreshed is not None

    # Emit 0-token local precheck card when both docs are ready (await user click before invoking LLM)
    if refreshed.tender_doc and refreshed.response_doc:
        if refreshed.checklist and refreshed.stage == "completed" and doc_role == "response":
            msg = append_message(
                project_id,
                "assistant",
                f"已更新响应文件 `{ast.filename}`（`{ast.total_pages}` 页 · 形式预警 `{len(ast.deterministic_findings)}` 处）。",
            )
            await EVENT_BUS.sync_and_broadcast_telemetry(project_id, stage="awaiting_confirm", stage_label="待复检")
            await EVENT_BUS.emit(project_id, "chat_message", msg.model_dump())
        else:
            t_ast_obj = ast if doc_role == "tender" else tender_ast
            r_ast_obj = ast if doc_role == "response" else r_ast
            if t_ast_obj is not None and r_ast_obj is not None:
                await emit_document_precheck(project_id, t_ast_obj, r_ast_obj)
            else:
                await EVENT_BUS.sync_and_broadcast_telemetry(project_id, stage="idle", stage_label="待生成清单")
    else:
        await EVENT_BUS.sync_and_broadcast_telemetry(project_id, stage="idle", stage_label="待导入文档")

    return {"project": get_project(project_id).model_dump()}  # type: ignore[union-attr]


@router.get("/workspace-samples")
async def list_workspace_samples() -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for p in sorted(BASE_DIR.iterdir()):
        if p.is_file() and p.suffix.lower() in (".docx", ".pdf") and not p.name.startswith("~$"):
            guessed_role = "response" if ("响应" in p.name or "投标" in p.name) else "tender"
            samples.append(
                {
                    "filename": p.name,
                    "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
                    "guessed_role": guessed_role,
                }
            )
    return {"samples": samples}


@router.get("/projects")
async def api_list_projects() -> dict[str, Any]:
    return {"projects": list_projects()}


@router.post("/projects")
async def api_create_project(req: CreateProjectReq) -> dict[str, Any]:
    proj = create_project(req.name)
    return {"project": proj.model_dump()}


@router.get("/projects/{project_id}")
async def api_get_project(project_id: str) -> dict[str, Any]:
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"project": proj.model_dump()}


@router.delete("/projects/{project_id}")
async def api_delete_project(project_id: str) -> dict[str, Any]:
    await cancel_project_task(project_id)
    ok = delete_project(project_id)
    if not ok:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"deleted": True}


@router.post("/projects/{project_id}/documents/upload")
async def api_upload_document(
    project_id: str,
    doc_role: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if doc_role not in ("tender", "response"):
        raise HTTPException(status_code=400, detail="doc_role 必须为 tender 或 response")
    orig_name = file.filename or f"{doc_role}.docx"
    ext = Path(orig_name).suffix.lower()
    if ext not in (".docx", ".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 .docx 与 .pdf 格式（老旧 .doc 请另存为 .docx）")

    ensure_data_dirs()
    proj_dir = UPLOADS_DIR / project_id
    proj_dir.mkdir(parents=True, exist_ok=True)
    safe_name = orig_name.replace("/", "_").replace("\\", "_")
    dest_path = proj_dir / f"{doc_role}_{safe_name}"

    # Stream 8MB chunks to disk without buffering 200MB in memory
    with dest_path.open("wb") as out_f:
        while True:
            chunk = await file.read(8 * 1024 * 1024)
            if not chunk:
                break
            out_f.write(chunk)

    return await _finalize_mounted_doc(project_id, doc_role, dest_path)


@router.post("/projects/{project_id}/documents/mount-local")
async def api_mount_local_sample(project_id: str, req: MountLocalDocReq) -> dict[str, Any]:
    target = (BASE_DIR / req.filename).resolve()
    if target.parent != BASE_DIR.resolve() or not target.exists() or target.suffix.lower() not in (".docx", ".pdf"):
        raise HTTPException(status_code=404, detail="未在工作区根目录找到指定标书文件")
    return await _finalize_mounted_doc(project_id, req.doc_role, target)


@router.patch("/projects/{project_id}/checklist/{item_id}")
async def api_toggle_checklist_item(project_id: str, item_id: str, req: ToggleItemReq) -> dict[str, Any]:
    proj = get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    target_item = next((it for it in proj.checklist if it.item_id == item_id), None)
    if not target_item:
        raise HTTPException(status_code=404, detail="检查项不存在")

    target_item.enabled = req.enabled
    upsert_checklist_item(project_id, target_item)
    enabled_cnt = sum(1 for it in proj.checklist if it.enabled)
    resp_ast = await asyncio.to_thread(_load_response_ast_if_cached, proj)
    est_tok, est_cost, est_sec = await asyncio.to_thread(
        _estimate_plan_metrics, proj.checklist, resp_ast
    )
    await EVENT_BUS.sync_and_broadcast_telemetry(
        project_id,
        total_items=enabled_cnt,
        estimated_plan_tokens=est_tok,
        estimated_plan_cost=est_cost,
        estimated_plan_seconds=est_sec,
    )
    await EVENT_BUS.emit(project_id, "item_updated", target_item.model_dump())
    return {"item": target_item.model_dump()}


@router.get("/projects/{project_id}/outline")
async def api_get_response_outline(project_id: str) -> dict[str, Any]:
    proj = get_project(project_id)
    if not proj or not proj.response_doc:
        return {"sections": [], "deterministic_findings": []}
    src = proj.response_doc.metadata.get("source_path", "")
    ast = await asyncio.to_thread(parse_and_cache_document, src, "response", proj.response_doc.doc_id)
    lite_sections = [
        {
            "section_id": s.section_id,
            "level": s.level,
            "title": s.title,
            "breadcrumb": s.breadcrumb,
            "page_label": s.page_label,
            "char_count": s.char_count,
            "table_count": len(s.tables),
            "image_count": len(s.media_ids) + sum(len(t.media_ids) for t in s.tables),
        }
        for s in ast.sections
    ]
    return {
        "sections": lite_sections,
        "deterministic_findings": [d.model_dump() for d in ast.deterministic_findings],
    }


@router.get("/projects/{project_id}/sections/{section_id}")
async def api_get_section_detail(project_id: str, section_id: str) -> dict[str, Any]:
    proj = get_project(project_id)
    if not proj or not proj.response_doc:
        raise HTTPException(status_code=404, detail="尚未挂载响应文件")
    src = proj.response_doc.metadata.get("source_path", "")
    ast = await asyncio.to_thread(parse_and_cache_document, src, "response", proj.response_doc.doc_id)
    sec = next((s for s in ast.sections if s.section_id == section_id), None)
    if not sec:
        raise HTTPException(status_code=404, detail="章节不存在")

    all_imgs = list(dict.fromkeys(sec.media_ids + [mid for t in sec.tables for mid in t.media_ids]))
    sec_dets = [d.model_dump() for d in ast.deterministic_findings if d.section_id == section_id]
    return {
        "section": {
            "section_id": sec.section_id,
            "level": sec.level,
            "title": sec.title,
            "breadcrumb": sec.breadcrumb,
            "page_label": sec.page_label,
            "paragraphs": sec.paragraphs,
            "tables": [t.model_dump() for t in sec.tables],
            "media_ids": all_imgs,
            "deterministic_findings": sec_dets,
        }
    }


@router.get("/projects/{project_id}/media/{media_id}")
async def api_get_media_preview(project_id: str, media_id: str) -> FileResponse:
    proj = get_project(project_id)
    if not proj or not proj.response_doc:
        raise HTTPException(status_code=404, detail="响应文件不存在")
    src = proj.response_doc.metadata.get("source_path", "")
    ast = await asyncio.to_thread(parse_and_cache_document, src, "response", proj.response_doc.doc_id)
    jpg_path = await asyncio.to_thread(extract_media_jpeg, ast, media_id, 1280, 82)
    if not jpg_path or not jpg_path.exists():
        raise HTTPException(status_code=404, detail="图片提取失败或不存在")
    return FileResponse(jpg_path, media_type="image/jpeg")
