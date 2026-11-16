"""Report Query and Offline Document Export (.html / .docx / .xlsx) Routes."""

from __future__ import annotations

import asyncio
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from backend.db import get_project

router = APIRouter(prefix="/api/projects/{project_id}/export", tags=["export"])


@router.get("/html")
async def export_report_html(project_id: str) -> FileResponse:
    proj = get_project(project_id)
    if not proj or (not proj.report and not proj.checklist):
        raise HTTPException(status_code=400, detail="当前项目尚未生成检查报告")

    from backend.exporters.html_exporter import build_html_report

    out_path = await asyncio.to_thread(build_html_report, proj)
    dl_name = f"{proj.name}_标书检查报告.html"
    return FileResponse(
        out_path,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(dl_name)}"},
    )


@router.get("/docx")
async def export_report_docx(project_id: str) -> FileResponse:
    proj = get_project(project_id)
    if not proj or not proj.report:
        raise HTTPException(status_code=400, detail="当前项目尚未生成检查报告")

    from backend.exporters.docx_exporter import build_docx_report

    out_path = await asyncio.to_thread(build_docx_report, proj)
    dl_name = f"{proj.name}_标书检查报告.docx"
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(dl_name)}"},
    )


@router.get("/xlsx")
async def export_report_xlsx(project_id: str) -> FileResponse:
    proj = get_project(project_id)
    if not proj or not proj.checklist:
        raise HTTPException(status_code=400, detail="当前项目尚未生成检查清单或报告")

    from backend.exporters.xlsx_exporter import build_xlsx_checklist

    out_path = await asyncio.to_thread(build_xlsx_checklist, proj)
    dl_name = f"{proj.name}_整改销项表.xlsx"
    return FileResponse(
        out_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(dl_name)}"},
    )
