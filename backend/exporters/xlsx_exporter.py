"""Excel (.xlsx) Team Remediation Checklist Generator using openpyxl."""

from __future__ import annotations

import asyncio
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from backend.config import REPORTS_DIR, ensure_data_dirs
from backend.parsers.indexer import parse_and_cache_document
from backend.schemas import (
    CATEGORY_LABELS,
    RISK_LABELS,
    STATUS_LABELS,
    ProjectDetail,
)


def build_xlsx_checklist(proj: ProjectDetail) -> Path:
    ensure_data_dirs()
    out_path = REPORTS_DIR / f"{proj.id}_checklist.xlsx"

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "条款整改销项表"

    thin = Side(border_style="thin", color="E5E7EB")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    hdr_fill = PatternFill(start_color="1D1D1F", end_color="1D1D1F", fill_type="solid")
    hdr_font = Font(name="PingFang SC", size=10, bold=True, color="FFFFFF")
    body_font = Font(name="PingFang SC", size=10, color="1D1D1F")

    fill_passed = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    fill_partial = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")
    fill_missing = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    headers = [
        "检查编号",
        "检查维度",
        "风险等级",
        "检查项标题",
        "响应状态",
        "我方响应页码与章节",
        "核查结论",
        "整改建议",
        "图面核验说明",
        "招标文件要求原文",
        "责任人(认领)",
        "销项状态",
    ]
    ws.append(headers)
    ws.freeze_panes = "A2"

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = hdr_fill
        cell.font = hdr_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 26

    # Sort problem items to the top for rapid team remediation!
    status_priority = {"missing": 0, "partial": 1, "unchecked": 2, "passed": 3}
    sorted_items = sorted(
        [it for it in proj.checklist if it.enabled],
        key=lambda x: (status_priority.get(x.compliance_status, 9), x.order_index),
    )

    for r_idx, it in enumerate(sorted_items, start=2):
        loc_str = " ; ".join(f"[{m.page_label}] {m.breadcrumb}" for m in it.matched_sections) or "未定位"
        sign_off_default = "无需整改" if it.compliance_status == "passed" else "待处理"
        row_vals = [
            it.item_id,
            CATEGORY_LABELS.get(it.category, it.category),
            RISK_LABELS.get(it.risk_level, it.risk_level),
            it.title,
            STATUS_LABELS.get(it.compliance_status, it.compliance_status),
            loc_str,
            it.conclusion,
            it.remediation,
            it.vision_note,
            it.requirement_text,
            "",
            sign_off_default,
        ]
        ws.append(row_vals)
        for c_idx in range(1, len(headers) + 1):
            c = ws.cell(row=r_idx, column=c_idx)
            c.font = body_font
            c.border = border
            c.alignment = Alignment(vertical="top", wrap_text=True)
            if c_idx == 5:
                c.alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
                if it.compliance_status == "passed":
                    c.fill = fill_passed
                elif it.compliance_status == "partial":
                    c.fill = fill_partial
                elif it.compliance_status == "missing":
                    c.fill = fill_missing

    col_widths = [11, 16, 11, 26, 12, 34, 38, 34, 24, 42, 14, 12]
    for idx, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = w
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(2, len(sorted_items) + 1)}"

    # Sheet 2: Deterministic Formal Redlines
    det_list = proj.report.deterministic_findings if proj.report else []
    if not det_list and proj.response_doc:
        src = proj.response_doc.metadata.get("source_path", "")
        if src and Path(src).exists():
            ast = parse_and_cache_document(src, "response", proj.response_doc.doc_id)
            det_list = ast.deterministic_findings

    ws2 = wb.create_sheet(title="内置形式与留空预警")
    h2 = ["编号", "严重程度", "规则类型", "页码区间", "章节路径", "预警标题", "详细说明", "原文片段"]
    ws2.append(h2)
    ws2.freeze_panes = "A2"
    for col_idx in range(1, len(h2) + 1):
        c = ws2.cell(row=1, column=col_idx)
        c.fill = hdr_fill
        c.font = hdr_font
        c.alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 24

    for r_idx, df in enumerate(det_list, start=2):
        ws2.append(
            [
                df.finding_id,
                "废标红线" if df.severity == "fatal" else ("重要提醒" if df.severity == "warning" else "提示"),
                df.rule_type,
                df.page_hint,
                df.breadcrumb,
                df.title,
                df.detail,
                df.snippet,
            ]
        )
        for c_idx in range(1, len(h2) + 1):
            c = ws2.cell(row=r_idx, column=c_idx)
            c.font = body_font
            c.border = border
            c.alignment = Alignment(vertical="top", wrap_text=True)
            if c_idx == 2:
                c.fill = fill_missing if df.severity == "fatal" else fill_partial

    w2 = [10, 12, 18, 12, 36, 30, 42, 36]
    for idx, w in enumerate(w2, start=1):
        ws2.column_dimensions[get_column_letter(idx)].width = w

    wb.save(str(out_path))
    return out_path
