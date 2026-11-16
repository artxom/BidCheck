"""Formal Word (.docx) Inspection Report Generator using python-docx."""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from backend.config import REPORTS_DIR, ensure_data_dirs
from backend.schemas import (
    CATEGORY_LABELS,
    RISK_LABELS,
    STATUS_LABELS,
    ProjectDetail,
)

_DEFAULT_CN_FONT = "Microsoft YaHei" if sys.platform == "win32" else "PingFang SC"


def _set_cn_font(run, font_name: str = _DEFAULT_CN_FONT, size_pt: float = 10.5, bold: bool = False, color: RGBColor | None = None) -> None:
    run.font.name = font_name
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
    run.font.size = Pt(size_pt)
    run.bold = bold
    if color:
        run.font.color.rgb = color


def build_docx_report(proj: ProjectDetail) -> Path:
    ensure_data_dirs()
    out_path = REPORTS_DIR / f"{proj.id}_report.docx"
    rep = proj.report
    assert rep is not None

    doc = Document()
    for section in doc.sections:
        section.top_margin = Cm(2.2)
        section.bottom_margin = Cm(2.2)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    # Title
    title_p = doc.add_paragraph()
    title_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_title = title_p.add_run(f"{proj.name} — 投标响应核查报告")
    _set_cn_font(r_title, size_pt=18, bold=True, color=RGBColor(0x1D, 0x1D, 0x1F))

    meta_p = doc.add_paragraph()
    meta_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_meta = meta_p.add_run(
        f"目标标段：{proj.target_lot or '全标段'}    |    就绪度评分：{rep.readiness_score}/100    |    生成时间：{rep.generated_at[:19].replace('T', ' ')}"
    )
    _set_cn_font(r_meta, size_pt=9.5, color=RGBColor(0x6E, 0x6E, 0x73))

    # Section 1: Executive Conclusion
    h1 = doc.add_paragraph()
    _set_cn_font(h1.add_run("一、总体核查结论与统计概览"), size_pt=13.5, bold=True)

    verdict_color = (
        RGBColor(0x15, 0x80, 0x3D)
        if rep.overall_verdict == "ready"
        else (RGBColor(0xB4, 0x53, 0x09) if rep.overall_verdict == "needs_fix" else RGBColor(0xDC, 0x26, 0x26))
    )
    vp = doc.add_paragraph()
    _set_cn_font(vp.add_run("封标评估结论："), size_pt=11, bold=True)
    _set_cn_font(vp.add_run(rep.verdict_label), size_pt=11, bold=True, color=verdict_color)

    sp = doc.add_paragraph()
    _set_cn_font(sp.add_run(rep.executive_summary), size_pt=10.5)

    # Category summary table
    if rep.category_stats:
        cat_tbl = doc.add_table(rows=1, cols=5)
        cat_tbl.style = "Table Grid"
        cat_tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdrs = ["检查维度", "条款总数", "已响应", "待补充/存疑", "未响应"]
        for idx, text in enumerate(hdrs):
            c = cat_tbl.rows[0].cells[idx]
            p = c.paragraphs[0]
            _set_cn_font(p.add_run(text), size_pt=9.5, bold=True)
        for cs in rep.category_stats:
            row = cat_tbl.add_row().cells
            vals = [cs.label, str(cs.total), str(cs.passed), str(cs.partial), str(cs.missing)]
            for idx, v in enumerate(vals):
                _set_cn_font(row[idx].paragraphs[0].add_run(v), size_pt=9.5)

    # Section 2: Priority Remediation Actions
    if rep.priority_actions:
        doc.add_paragraph()
        h2 = doc.add_paragraph()
        _set_cn_font(h2.add_run("二、封标前优先整改事项"), size_pt=13.5, bold=True)
        for idx, act in enumerate(rep.priority_actions, start=1):
            ap = doc.add_paragraph()
            _set_cn_font(ap.add_run(f"{idx}. {act}"), size_pt=10.5)

    # Section 3: Deterministic Formal Redlines
    if rep.deterministic_findings:
        doc.add_paragraph()
        h3 = doc.add_paragraph()
        _set_cn_font(h3.add_run("三、系统固有形式与留空扫描预警"), size_pt=13.5, bold=True)
        det_tbl = doc.add_table(rows=1, cols=4)
        det_tbl.style = "Table Grid"
        for idx, text in enumerate(["级别", "页码", "章节位置", "预警问题与说明"]):
            _set_cn_font(det_tbl.rows[0].cells[idx].paragraphs[0].add_run(text), size_pt=9.5, bold=True)
        for d in rep.deterministic_findings:
            rc = det_tbl.add_row().cells
            sev_map = {"fatal": "废标红线", "warning": "重要提醒", "info": "提示"}
            _set_cn_font(rc[0].paragraphs[0].add_run(sev_map.get(d.severity, d.severity)), size_pt=9)
            _set_cn_font(rc[1].paragraphs[0].add_run(d.page_hint), size_pt=9)
            _set_cn_font(rc[2].paragraphs[0].add_run(d.breadcrumb), size_pt=9)
            _set_cn_font(rc[3].paragraphs[0].add_run(f"{d.title}：{d.detail}"), size_pt=9)

    # Section 4: Clause-by-Clause Detailed Table
    doc.add_paragraph()
    h4 = doc.add_paragraph()
    _set_cn_font(h4.add_run("四、招标要求逐项核查明细表"), size_pt=13.5, bold=True)

    enabled_items = [it for it in proj.checklist if it.enabled]
    item_tbl = doc.add_table(rows=1, cols=6)
    item_tbl.style = "Table Grid"
    cols_hdr = ["编号", "维度/风险", "检查项与招标要求", "响应状态", "我方响应定位", "核查结论与建议"]
    for idx, text in enumerate(cols_hdr):
        _set_cn_font(item_tbl.rows[0].cells[idx].paragraphs[0].add_run(text), size_pt=9, bold=True)

    for it in enabled_items:
        rc = item_tbl.add_row().cells
        _set_cn_font(rc[0].paragraphs[0].add_run(it.item_id), size_pt=8.5)
        _set_cn_font(
            rc[1].paragraphs[0].add_run(
                f"{CATEGORY_LABELS.get(it.category, it.category)}\n[{RISK_LABELS.get(it.risk_level, it.risk_level)}]"
            ),
            size_pt=8.5,
        )
        _set_cn_font(
            rc[2].paragraphs[0].add_run(f"【{it.title}】\n{it.requirement_text}"),
            size_pt=8.5,
        )

        st_color = (
            RGBColor(0x15, 0x80, 0x3D)
            if it.compliance_status == "passed"
            else (RGBColor(0xB4, 0x53, 0x09) if it.compliance_status == "partial" else RGBColor(0xDC, 0x26, 0x26))
        )
        _set_cn_font(
            rc[3].paragraphs[0].add_run(STATUS_LABELS.get(it.compliance_status, it.compliance_status)),
            size_pt=9,
            bold=True,
            color=st_color,
        )

        loc_text = "\n".join(f"{m.page_label} {m.breadcrumb}" for m in it.matched_sections[:3]) or "未定位"
        _set_cn_font(rc[4].paragraphs[0].add_run(loc_text), size_pt=8.5)

        conc = it.conclusion
        if it.vision_note:
            conc += f"\n[验图] {it.vision_note}"
        if it.remediation and it.compliance_status != "passed":
            conc += f"\n[整改] {it.remediation}"
        _set_cn_font(rc[5].paragraphs[0].add_run(conc), size_pt=8.5)

    doc.save(str(out_path))
    return out_path
