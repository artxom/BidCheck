"""PDF (.pdf) parser using PyMuPDF (fitz) producing the unified DocumentAST."""

from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import pymupdf as fitz  # PyMuPDF
from PIL import Image

from backend.config import MEDIA_CACHE_DIR, ensure_data_dirs
from backend.parsers.models import DocumentAST, MediaRef, SectionNode, TableBlock

CN_HEAD_H1 = re.compile(r"^(第[一二三四五六七八九十百0-9]+[章节篇部分]|附件\s*[0-9一二三四五六七八九十]*)[\s：:、.]*\S+")
CN_HEAD_H2 = re.compile(r"^([一二三四五六七八九十]{1,3}[、.．]|\d+\.\d*\s+\S+)\s*")


def parse_pdf(file_path: str | Path, doc_role: str, doc_id: str) -> DocumentAST:
    """Parse a PDF document into hierarchical SectionNodes with exact physical page numbers."""
    path = Path(file_path)
    file_size = path.stat().st_size

    doc = fitz.open(path)
    total_pages = len(doc)
    raw_toc = doc.get_toc()  # [[lvl, title, page], ...]
    toc_entries: list[dict[str, Any]] = [
        {"title": str(item[1]).strip(), "page": int(item[2]), "level": int(item[0])}
        for item in raw_toc
        if len(item) >= 3 and str(item[1]).strip()
    ]

    # Map page_num (1-based) -> list of (level, title) from PDF bookmarks if available
    toc_by_page: dict[int, list[tuple[int, str]]] = {}
    for entry in toc_entries:
        toc_by_page.setdefault(entry["page"], []).append((min(entry["level"], 5), entry["title"]))

    sections: list[SectionNode] = []
    media_index: dict[str, MediaRef] = {}
    cover_lines: list[str] = []
    heading_stack: list[tuple[int, str, str]] = []
    sec_counter = 0
    tbl_counter = 0
    img_counter = 0

    current_section = SectionNode(
        section_id="sec_0000",
        order_index=0,
        level=0,
        title="封面与前导页",
        breadcrumb="封面与前导页",
        page_start=1,
        page_end=1,
    )
    sections.append(current_section)

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc[page_idx]
        text = page.get_text("text") or ""
        lines = [re.sub(r"[ \t\u3000]+", " ", ln).strip() for ln in text.splitlines()]
        lines = [ln for ln in lines if ln]

        if page_num <= 2 and len(cover_lines) < 35:
            cover_lines.extend(lines[:20])

        # Create sections from PDF outline bookmarks starting on this page
        if page_num in toc_by_page:
            for lvl, b_title in toc_by_page[page_num]:
                while heading_stack and heading_stack[-1][0] >= lvl:
                    heading_stack.pop()
                parent_id = heading_stack[-1][1] if heading_stack else None
                sec_counter += 1
                sid = f"sec_{sec_counter:04d}"
                heading_stack.append((lvl, sid, b_title))
                breadcrumb = " > ".join(x[2] for x in heading_stack)
                current_section = SectionNode(
                    section_id=sid,
                    order_index=sec_counter,
                    level=lvl,
                    title=b_title,
                    breadcrumb=breadcrumb,
                    parent_id=parent_id,
                    page_start=page_num,
                    page_end=page_num,
                )
                sections.append(current_section)

        for ln in lines:
            # If PDF lacks outline bookmarks, infer headings via Chinese numbering
            if not toc_entries and len(ln) <= 68 and not ln.endswith(("。", "；", "：", ":")):
                inferred_lvl: int | None = None
                if CN_HEAD_H1.match(ln):
                    inferred_lvl = 1
                elif CN_HEAD_H2.match(ln):
                    inferred_lvl = 2
                if inferred_lvl is not None:
                    while heading_stack and heading_stack[-1][0] >= inferred_lvl:
                        heading_stack.pop()
                    parent_id = heading_stack[-1][1] if heading_stack else None
                    sec_counter += 1
                    sid = f"sec_{sec_counter:04d}"
                    heading_stack.append((inferred_lvl, sid, ln))
                    breadcrumb = " > ".join(x[2] for x in heading_stack)
                    current_section = SectionNode(
                        section_id=sid,
                        order_index=sec_counter,
                        level=inferred_lvl,
                        title=ln,
                        breadcrumb=breadcrumb,
                        parent_id=parent_id,
                        page_start=page_num,
                        page_end=page_num,
                    )
                    sections.append(current_section)
                    continue

            current_section.paragraphs.append(ln)
            current_section.char_count += len(ln)
            current_section.page_end = max(current_section.page_end or page_num, page_num)

        # Extract tables on page (lightweight guard)
        try:
            tabs = page.find_tables()
            for tab in tabs.tables:
                extracted = tab.extract()
                if not extracted or len(extracted) < 2:
                    continue
                rows_grid = [
                    [re.sub(r"\s+", " ", (cell or "")).strip() for cell in row]
                    for row in extracted
                ]
                max_cols = max((len(r) for r in rows_grid), default=0)
                if max_cols < 2:
                    continue
                tbl_counter += 1
                tid = f"tbl_{tbl_counter:04d}"
                md_lines = [
                    "| " + " | ".join(c.replace("|", "｜")[:160] for c in rows_grid[0]) + " |",
                    "| " + " | ".join(["---"] * max_cols) + " |",
                ]
                for r in rows_grid[1:]:
                    md_lines.append("| " + " | ".join(c.replace("|", "｜")[:160] for c in r) + " |")
                tb = TableBlock(
                    table_id=tid,
                    section_id=current_section.section_id,
                    row_count=len(rows_grid),
                    col_count=max_cols,
                    headers=rows_grid[0],
                    rows=rows_grid,
                    markdown="\n".join(md_lines),
                    page_hint=f"P{page_num}",
                )
                current_section.tables.append(tb)
                current_section.char_count += len(tb.markdown)
        except Exception:
            pass

        # Record embedded images on page (skipping tiny decorative icons < 80px)
        try:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                w_px = int(img_info[2] or 0)
                h_px = int(img_info[3] or 0)
                if w_px < 80 and h_px < 80:
                    continue
                img_counter += 1
                mid = f"img_{img_counter:04d}"
                media_index[mid] = MediaRef(
                    media_id=mid,
                    rel_id=str(xref),
                    source_key=f"pdf:{page_idx}:{xref}",
                    ext=".jpg",
                    width_px=w_px,
                    height_px=h_px,
                    section_id=current_section.section_id,
                    breadcrumb=current_section.breadcrumb,
                    page_hint=f"P{page_num}",
                    context_text=current_section.title[:100],
                )
                current_section.media_ids.append(mid)
        except Exception:
            pass

    doc.close()

    for i, sec in enumerate(sections):
        if i + 1 < len(sections):
            nxt = sections[i + 1].page_start or sec.page_start or 1
            sec.page_end = max(sec.page_start or 1, nxt)
        else:
            sec.page_end = max(sec.page_start or 1, total_pages)

    total_chars = sum(s.char_count for s in sections)
    return DocumentAST(
        doc_id=doc_id,
        filename=path.name,
        source_path=str(path.resolve()),
        file_type="pdf",
        doc_role=doc_role,  # type: ignore[arg-type]
        file_size_bytes=file_size,
        total_pages=total_pages,
        total_chars=total_chars,
        total_tables=tbl_counter,
        total_images=len(media_index),
        cover_lines=cover_lines,
        toc_entries=toc_entries,
        sections=sections,
        media_index=media_index,
    )


def extract_pdf_media_jpeg(
    pdf_path: str | Path,
    doc_id: str,
    media_ref: MediaRef,
    max_side: int = 1280,
    quality: int = 80,
) -> Path | None:
    """Lazily extract a PDF image xref or render page snapshot to compressed JPEG."""
    ensure_data_dirs()
    out_dir = MEDIA_CACHE_DIR / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{media_ref.media_id}_{max_side}.jpg"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    try:
        doc = fitz.open(pdf_path)
        parts = media_ref.source_key.split(":")
        xref = int(parts[2]) if len(parts) >= 3 else int(media_ref.rel_id)
        base_img = doc.extract_image(xref)
        raw_bytes = base_img["image"]
        doc.close()

        with Image.open(io.BytesIO(raw_bytes)) as im:
            rgb = im.convert("RGB")
            w, h = rgb.size
            if max(w, h) > max_side:
                scale = max_side / float(max(w, h))
                rgb = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
            rgb.save(out_path, format="JPEG", quality=quality, optimize=True)
        return out_path
    except Exception:
        return None
