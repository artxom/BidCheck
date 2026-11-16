"""High-performance native OOXML (.docx) parser with TOC PAGEREF page anchoring and lazy media extraction."""

from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path
from typing import Any

from lxml import etree
from PIL import Image

from backend.config import MEDIA_CACHE_DIR, ensure_data_dirs
from backend.parsers.models import (
    DocumentAST,
    EmptyCellAlert,
    MediaRef,
    SectionNode,
    TableBlock,
)

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

NS = {"w": W_NS, "r": R_NS, "a": A_NS, "wp": WP_NS}
W_VAL = f"{{{W_NS}}}val"
W_ID = f"{{{W_NS}}}id"
W_NAME = f"{{{W_NS}}}name"
W_TYPE = f"{{{W_NS}}}type"
R_EMBED = f"{{{R_NS}}}embed"

EMU_PER_PX = 9525  # 914400 EMU/inch @ 96 DPI

# Heuristic Chinese heading patterns for unstyled paragraphs (especially in tender docs)
CN_H1_RE = re.compile(r"^(第[一二三四五六七八九十百0-9]+[章节篇部分]|附件\s*[0-9一二三四五六七八九十]*)[\s：:、.]*\S+")
CN_H2_RE = re.compile(r"^([一二三四五六七八九十]{1,3}[、.．])\s*\S+")
CN_LOT_RE = re.compile(r"^([A-Z0-9]+\s*[标分][段包号]|[标分][段包号]\s*[A-Z0-9]+)\s*[：:、—-]?\s*\S*")
PAGEREF_RE = re.compile(r"PAGEREF\s+([^\s\\]+)")
TRAILING_PAGE_RE = re.compile(r"(\d{1,4})\s*$")


def _clean_text(text: str) -> str:
    return re.sub(r"[ \t\u3000]+", " ", text).strip()


def _parse_styles(zf: zipfile.ZipFile) -> dict[str, tuple[str, int | None]]:
    """Return styleId -> (styleName, outlineLvl 0-based or None)."""
    styles_map: dict[str, tuple[str, int | None]] = {}
    if "word/styles.xml" not in zf.namelist():
        return styles_map
    root = etree.fromstring(zf.read("word/styles.xml"))
    raw_styles: dict[str, tuple[str, int | None, str | None]] = {}
    for st in root.findall(f"{{{W_NS}}}style"):
        sid = st.get(f"{{{W_NS}}}styleId")
        if not sid:
            continue
        name_el = st.find(f"{{{W_NS}}}name")
        sname = name_el.get(W_VAL, sid) if name_el is not None else sid
        based_el = st.find(f"{{{W_NS}}}basedOn")
        based_on = based_el.get(W_VAL) if based_el is not None else None
        olvl: int | None = None
        ppr = st.find(f"{{{W_NS}}}pPr")
        if ppr is not None:
            ol_el = ppr.find(f"{{{W_NS}}}outlineLvl")
            if ol_el is not None and ol_el.get(W_VAL, "").isdigit():
                val = int(ol_el.get(W_VAL))
                if 0 <= val <= 8:
                    olvl = val
        if olvl is None:
            m = re.match(r"^heading\s*(\d)$", sname.strip(), re.IGNORECASE)
            if m:
                olvl = int(m.group(1)) - 1
        raw_styles[sid] = (sname, olvl, based_on)

    # Resolve single-hop/multi-hop inheritance for outlineLvl
    for sid, (sname, olvl, based_on) in raw_styles.items():
        cur_olvl = olvl
        visited = {sid}
        parent = based_on
        while cur_olvl is None and parent and parent not in visited and parent in raw_styles:
            visited.add(parent)
            _, p_olvl, parent = raw_styles[parent]
            cur_olvl = p_olvl
        styles_map[sid] = (sname, cur_olvl)
    return styles_map


def _parse_rels(zf: zipfile.ZipFile, rels_path: str = "word/_rels/document.xml.rels") -> dict[str, str]:
    """Return rId -> normalized zip path (e.g. 'word/media/image1.png') for standard images."""
    rels_map: dict[str, str] = {}
    if rels_path not in zf.namelist():
        return rels_map
    root = etree.fromstring(zf.read(rels_path))
    for rel in root.findall(f"{{{REL_NS}}}Relationship"):
        rid = rel.get("Id", "")
        rtype = rel.get("Type", "")
        target = rel.get("Target", "")
        if not rid or not target:
            continue
        # Only track primary image relationships (skipping Office 2010 hdphoto .wdp effect duplicates)
        if rtype.endswith("/image"):
            norm = target.lstrip("/")
            if not norm.startswith("word/"):
                norm = os.path.normpath(os.path.join("word", norm)).replace("\\", "/")
            rels_map[rid] = norm
    return rels_map


def _parse_app_pages(zf: zipfile.ZipFile) -> int:
    if "docProps/app.xml" not in zf.namelist():
        return 0
    try:
        root = etree.fromstring(zf.read("docProps/app.xml"))
        for el in root:
            if el.tag.endswith("Pages") and el.text and el.text.strip().isdigit():
                return int(el.text.strip())
    except Exception:
        pass
    return 0


def _extract_headers_footers(zf: zipfile.ZipFile) -> list[str]:
    texts: list[str] = []
    seen: set[str] = set()
    for name in sorted(zf.namelist()):
        if re.match(r"^word/(header|footer)\d*\.xml$", name):
            try:
                root = etree.fromstring(zf.read(name))
                for p in root.iter(f"{{{W_NS}}}p"):
                    line = _clean_text("".join(t.text or "" for t in p.iter(f"{{{W_NS}}}t")))
                    if line and line not in seen and not line.isdigit():
                        seen.add(line)
                        texts.append(line)
            except Exception:
                continue
    return texts


def _extract_drawings_from_element(
    el: etree._Element,
    rels_map: dict[str, str],
    media_index: dict[str, MediaRef],
    media_counter: list[int],
    section_id: str,
    breadcrumb: str,
    context_text: str,
) -> list[str]:
    found_ids: list[str] = []
    for drawing in el.findall(f".//{{{W_NS}}}drawing"):
        # Primary image blip (do NOT pick a14:imgLayer hdphoto duplicates)
        blip = drawing.find(f".//{{{A_NS}}}blip")
        if blip is None:
            continue
        rid = blip.get(R_EMBED, "")
        if not rid or rid not in rels_map:
            continue
        zip_target = rels_map[rid]
        ext = os.path.splitext(zip_target)[1].lower() or ".png"

        width_px, height_px = 0, 0
        extent = drawing.find(f".//{{{WP_NS}}}extent")
        if extent is None:
            extent = drawing.find(f".//{{{A_NS}}}ext")
        if extent is not None:
            try:
                cx = int(extent.get("cx", "0"))
                cy = int(extent.get("cy", "0"))
                width_px = max(1, cx // EMU_PER_PX) if cx > 0 else 0
                height_px = max(1, cy // EMU_PER_PX) if cy > 0 else 0
            except ValueError:
                pass

        media_counter[0] += 1
        mid = f"img_{media_counter[0]:04d}"
        media_index[mid] = MediaRef(
            media_id=mid,
            rel_id=rid,
            source_key=zip_target,
            ext=ext,
            width_px=width_px,
            height_px=height_px,
            section_id=section_id,
            breadcrumb=breadcrumb,
            context_text=context_text[:120],
        )
        found_ids.append(mid)
    return found_ids


def _parse_table(
    tbl_el: etree._Element,
    table_id: str,
    section_id: str,
    breadcrumb: str,
    rels_map: dict[str, str],
    media_index: dict[str, MediaRef],
    media_counter: list[int],
) -> TableBlock:
    rows_grid: list[list[str]] = []
    table_media_ids: list[str] = []
    vmerge_memory: dict[int, str] = {}

    for tr in tbl_el.findall(f"{{{W_NS}}}tr"):
        row_cells: list[str] = []
        col_cursor = 0
        for tc in tr.findall(f"{{{W_NS}}}tc"):
            tc_pr = tc.find(f"{{{W_NS}}}tcPr")
            span = 1
            vmerge_state: str | None = None  # None | 'restart' | 'continue'
            if tc_pr is not None:
                gs = tc_pr.find(f"{{{W_NS}}}gridSpan")
                if gs is not None and gs.get(W_VAL, "").isdigit():
                    span = max(1, int(gs.get(W_VAL)))
                vm = tc_pr.find(f"{{{W_NS}}}vMerge")
                if vm is not None:
                    vmerge_state = vm.get(W_VAL, "continue")

            # Gather paragraph lines inside cell (skipping nested table text duplication by reading direct paragraphs + nested briefly)
            cell_lines: list[str] = []
            for p in tc.findall(f".//{{{W_NS}}}p"):
                ptxt = _clean_text("".join(t.text or "" for t in p.findall(f".//{{{W_NS}}}t")))
                if ptxt:
                    cell_lines.append(ptxt)
            cell_text = " / ".join(cell_lines)

            # Check images inside cell
            cell_imgs = _extract_drawings_from_element(
                tc,
                rels_map,
                media_index,
                media_counter,
                section_id,
                breadcrumb,
                context_text=cell_text or f"表格 {table_id}",
            )
            if cell_imgs:
                table_media_ids.extend(cell_imgs)
                img_tag = f"[内嵌图片×{len(cell_imgs)}: {','.join(cell_imgs)}]"
                cell_text = f"{cell_text} {img_tag}".strip()

            if vmerge_state == "continue" and not cell_text:
                cell_text = vmerge_memory.get(col_cursor, "")
            elif vmerge_state == "restart" or vmerge_state is None:
                vmerge_memory[col_cursor] = cell_text

            for s_idx in range(span):
                row_cells.append(cell_text if s_idx == 0 else cell_text)
                col_cursor += 1

        if row_cells:
            rows_grid.append(row_cells)

    max_cols = max((len(r) for r in rows_grid), default=0)
    for r in rows_grid:
        if len(r) < max_cols:
            r.extend([""] * (max_cols - len(r)))

    headers = rows_grid[0] if rows_grid else []
    empty_alerts: list[EmptyCellAlert] = []

    # Detect empty cells in structured tables (skipping tiny 1-row tables or pure layout tables)
    if len(rows_grid) >= 2 and max_cols >= 2:
        for r_idx, r in enumerate(rows_grid[1:], start=1):
            non_empty_in_row = [c for c in r if c.strip()]
            if not non_empty_in_row:
                continue
            row_ctx = " | ".join(c for c in r[:2] if c)[:60]
            for c_idx, val in enumerate(r):
                hdr = headers[c_idx] if c_idx < len(headers) else f"列{c_idx+1}"
                if not val.strip() and hdr and not any(skip in hdr for skip in ("备注", "说明")):
                    if len(empty_alerts) < 25:
                        empty_alerts.append(
                            EmptyCellAlert(
                                row_idx=r_idx + 1,
                                col_idx=c_idx + 1,
                                col_header=hdr[:30],
                                row_context=row_ctx,
                            )
                        )

    # Render compact Markdown table (cap cell width for clean LLM reading)
    md_lines: list[str] = []
    if rows_grid and max_cols > 0:
        def _fmt_row(cells: list[str]) -> str:
            escaped = [c.replace("|", "｜").replace("\n", " ")[:180] for c in cells]
            return "| " + " | ".join(escaped) + " |"

        md_lines.append(_fmt_row(rows_grid[0]))
        md_lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        for r in rows_grid[1:]:
            md_lines.append(_fmt_row(r))

    return TableBlock(
        table_id=table_id,
        section_id=section_id,
        row_count=len(rows_grid),
        col_count=max_cols,
        headers=headers,
        rows=rows_grid,
        markdown="\n".join(md_lines),
        media_ids=table_media_ids,
        empty_cells=empty_alerts,
    )


def parse_docx(file_path: str | Path, doc_role: str, doc_id: str) -> DocumentAST:
    """Stream-parse a .docx file into a hierarchical DocumentAST with page anchors."""
    path = Path(file_path)
    file_size = path.stat().st_size

    with zipfile.ZipFile(path, "r") as zf:
        styles_map = _parse_styles(zf)
        rels_map = _parse_rels(zf)
        app_pages = _parse_app_pages(zf)
        headers_footers = _extract_headers_footers(zf)

        doc_xml_bytes = zf.read("word/document.xml")
        parser = etree.XMLParser(huge_tree=True, recover=True)
        root = etree.fromstring(doc_xml_bytes, parser=parser)

    body = root.find(f"{{{W_NS}}}body")
    if body is None:
        raise ValueError(f"Invalid .docx file (missing w:body): {path.name}")

    # Pass 1: Extract TOC PAGEREF bookmark -> cached page number mapping
    bookmark_to_page: dict[str, int] = {}
    toc_entries: list[dict[str, Any]] = []
    has_rendered_pb = False

    for p in body.iter(f"{{{W_NS}}}p"):
        if p.find(f".//{{{W_NS}}}lastRenderedPageBreak") is not None:
            has_rendered_pb = True
        instr_texts = "".join(it.text or "" for it in p.findall(f".//{{{W_NS}}}instrText"))
        hl_anchor = ""
        hl = p.find(f".//{{{W_NS}}}hyperlink")
        if hl is not None:
            hl_anchor = hl.get(f"{{{W_NS}}}anchor", "")

        bm_target = ""
        m_pr = PAGEREF_RE.search(instr_texts)
        if m_pr:
            bm_target = m_pr.group(1)
        elif hl_anchor.startswith("_Toc"):
            bm_target = hl_anchor

        if bm_target:
            # Extract page number specifically from the last text run (or after <w:tab/> / fldChar separate)
            runs_texts: list[str] = []
            for r_el in p.iter(f"{{{W_NS}}}r"):
                if r_el.find(f"{{{W_NS}}}tab") is not None:
                    runs_texts.append("\t")
                rt = "".join(t.text or "" for t in r_el.findall(f"{{{W_NS}}}t"))
                if rt:
                    runs_texts.append(rt)
            raw_joined = "".join(runs_texts).strip()
            if "\t" in raw_joined:
                head_part, tail_part = raw_joined.rsplit("\t", 1)
            else:
                # Fallback: inspect only final non-empty w:t element
                t_nodes = [t.text.strip() for t in p.findall(f".//{{{W_NS}}}t") if t.text and t.text.strip()]
                tail_part = t_nodes[-1] if t_nodes else ""
                head_part = "".join(t_nodes[:-1]) if len(t_nodes) > 1 else ""

            m_page = re.match(r"^(\d{1,4})$", tail_part.strip())
            if not m_page:
                m_page = TRAILING_PAGE_RE.search(tail_part.strip())
            if m_page:
                page_num = int(m_page.group(1))
                title_part = _clean_text(head_part).rstrip(".… \t")
                if 1 <= page_num <= 5000:
                    bookmark_to_page[bm_target] = page_num
                    if title_part:
                        toc_entries.append({"title": title_part, "page": page_num, "bookmark": bm_target})

    # Pass 2: Walk top-level children of w:body to construct hierarchical SectionNodes
    sections: list[SectionNode] = []
    media_index: dict[str, MediaRef] = {}
    media_counter = [0]
    table_counter = 0
    sec_counter = 0

    # Stack of (level, section_id, title)
    heading_stack: list[tuple[int, str, str]] = []
    cover_lines: list[str] = []

    current_section = SectionNode(
        section_id="sec_0000",
        order_index=0,
        level=0,
        title="封面与前导页",
        breadcrumb="封面与前导页",
        page_start=1,
    )
    sections.append(current_section)

    physical_page = 1  # Used if has_rendered_pb is True
    in_toc_zone = False

    for child in body:
        tag = etree.QName(child.tag).localname if isinstance(child.tag, str) else ""

        if tag == "sdt":
            # Structured Document Tag (often wraps Word's auto-generated TOC block)
            sdt_content = child.find(f"{{{W_NS}}}sdtContent")
            children_to_iter = list(sdt_content) if sdt_content is not None else []
        else:
            children_to_iter = [child]

        for block in children_to_iter:
            btag = etree.QName(block.tag).localname if isinstance(block.tag, str) else ""

            if btag == "p":
                if has_rendered_pb:
                    pb_cnt = len(block.findall(f".//{{{W_NS}}}lastRenderedPageBreak")) + len(
                        block.findall(f".//{{{W_NS}}}br[@{{{W_NS}}}type='page']")
                    )
                    physical_page += pb_cnt

                # Check bookmarkStarts in this paragraph for TOC page anchors
                anchored_page: int | None = None
                for bm in block.findall(f".//{{{W_NS}}}bookmarkStart"):
                    bname = bm.get(W_NAME, "")
                    if bname in bookmark_to_page:
                        anchored_page = bookmark_to_page[bname]
                        break

                p_pr = block.find(f"{{{W_NS}}}pPr")
                sid: str | None = None
                direct_olvl: int | None = None
                if p_pr is not None:
                    ps = p_pr.find(f"{{{W_NS}}}pStyle")
                    if ps is not None:
                        sid = ps.get(W_VAL)
                    ol = p_pr.find(f"{{{W_NS}}}outlineLvl")
                    if ol is not None and ol.get(W_VAL, "").isdigit():
                        val = int(ol.get(W_VAL))
                        if 0 <= val <= 8:
                            direct_olvl = val

                sname, style_olvl = styles_map.get(sid or "", (sid or "", None))
                eff_olvl = direct_olvl if direct_olvl is not None else style_olvl

                # Skip TOC listing lines from becoming fake body paragraphs
                instr = "".join(it.text or "" for it in block.findall(f".//{{{W_NS}}}instrText"))
                is_toc_line = (
                    "PAGEREF" in instr
                    or "TOC " in instr
                    or (sname and ("toc" in sname.lower() or sname.startswith("目录")))
                )
                txt = _clean_text("".join(t.text or "" for t in block.findall(f".//{{{W_NS}}}t")))

                if txt in ("目 录", "目录"):
                    in_toc_zone = True
                    continue
                if is_toc_line:
                    continue
                if in_toc_zone and eff_olvl is not None:
                    in_toc_zone = False

                # Fallback heuristic heading detection for unstyled tender/response headings
                heuristic_lvl: int | None = None
                if eff_olvl is None and txt and len(txt) <= 72 and not txt.endswith(("。", "；", "：", ":")):
                    if CN_H1_RE.match(txt):
                        heuristic_lvl = 0
                    elif CN_LOT_RE.match(txt):
                        heuristic_lvl = 1
                    elif CN_H2_RE.match(txt) and doc_role == "tender":
                        heuristic_lvl = 1

                final_olvl = eff_olvl if eff_olvl is not None else heuristic_lvl

                # Treat levels 0..5 (H1..H6) with non-empty text as SectionNode boundaries
                if final_olvl is not None and final_olvl <= 5 and txt:
                    in_toc_zone = False
                    lvl = final_olvl + 1  # 1..6
                    while heading_stack and heading_stack[-1][0] >= lvl:
                        heading_stack.pop()
                    parent_id = heading_stack[-1][1] if heading_stack else None
                    sec_counter += 1
                    new_sec_id = f"sec_{sec_counter:04d}"
                    heading_stack.append((lvl, new_sec_id, txt))
                    breadcrumb = " > ".join(item[2] for item in heading_stack)

                    sec_page = anchored_page or (physical_page if has_rendered_pb else None)
                    current_section = SectionNode(
                        section_id=new_sec_id,
                        order_index=sec_counter,
                        level=lvl,
                        title=txt,
                        breadcrumb=breadcrumb,
                        parent_id=parent_id,
                        page_start=sec_page,
                    )
                    sections.append(current_section)

                    # Heading itself might also contain an inline image/stamp
                    imgs = _extract_drawings_from_element(
                        block,
                        rels_map,
                        media_index,
                        media_counter,
                        current_section.section_id,
                        current_section.breadcrumb,
                        context_text=txt,
                    )
                    if imgs:
                        current_section.media_ids.extend(imgs)
                    continue

                # Regular body paragraph
                if anchored_page and current_section.page_start is None:
                    current_section.page_start = anchored_page

                imgs = _extract_drawings_from_element(
                    block,
                    rels_map,
                    media_index,
                    media_counter,
                    current_section.section_id,
                    current_section.breadcrumb,
                    context_text=txt or current_section.title,
                )
                if imgs:
                    current_section.media_ids.extend(imgs)

                if txt:
                    if current_section.level == 0 and len(cover_lines) < 35:
                        cover_lines.append(txt)
                    current_section.paragraphs.append(txt)
                    current_section.char_count += len(txt)

            elif btag == "tbl":
                table_counter += 1
                tid = f"tbl_{table_counter:04d}"
                tbl_block = _parse_table(
                    block,
                    tid,
                    current_section.section_id,
                    current_section.breadcrumb,
                    rels_map,
                    media_index,
                    media_counter,
                )
                current_section.tables.append(tbl_block)
                current_section.char_count += len(tbl_block.markdown)

    # Pass 3: Fallback TOC Title -> Section Page Matching (if bookmark names changed on save)
    if toc_entries:
        toc_by_norm_title: dict[str, int] = {}
        for entry in toc_entries:
            # Strip leading numbering like "7.1.1 " for fuzzy fallback
            raw_t = entry["title"]
            norm_t = re.sub(r"^[\d.、\s]+", "", raw_t).strip()
            if norm_t and norm_t not in toc_by_norm_title:
                toc_by_norm_title[norm_t] = entry["page"]
        for sec in sections:
            if sec.page_start is None and sec.level > 0:
                norm_s = re.sub(r"^[\d.、\s]+", "", sec.title).strip()
                if norm_s in toc_by_norm_title:
                    sec.page_start = toc_by_norm_title[norm_s]

    # Pass 4: Monotonic Page Range Propagation across all sections
    max_toc_page = max((e["page"] for e in toc_entries), default=0)
    total_pages = max(app_pages, physical_page if has_rendered_pb else 0, max_toc_page, 1)

    # Forward fill missing page_start
    last_known_page = 1
    for sec in sections:
        if sec.page_start is not None:
            last_known_page = max(last_known_page, sec.page_start)
        else:
            sec.page_start = last_known_page

    # Compute page_end from next section's page_start
    for i, sec in enumerate(sections):
        next_page = total_pages
        for j in range(i + 1, len(sections)):
            cand = sections[j].page_start
            if cand is not None and cand >= (sec.page_start or 1):
                next_page = cand
                break
        sec.page_end = max(sec.page_start or 1, next_page)
        p_label = sec.page_label
        for tbl in sec.tables:
            tbl.page_hint = p_label
        for mid in sec.media_ids:
            if mid in media_index:
                media_index[mid].page_hint = p_label
        for tbl in sec.tables:
            for mid in tbl.media_ids:
                if mid in media_index:
                    media_index[mid].page_hint = p_label

    total_chars = sum(s.char_count for s in sections)
    return DocumentAST(
        doc_id=doc_id,
        filename=path.name,
        source_path=str(path.resolve()),
        file_type="docx",
        doc_role=doc_role,  # type: ignore[arg-type]
        file_size_bytes=file_size,
        total_pages=total_pages,
        total_chars=total_chars,
        total_tables=table_counter,
        total_images=len(media_index),
        cover_lines=cover_lines,
        headers_footers=headers_footers,
        toc_entries=toc_entries,
        sections=sections,
        media_index=media_index,
    )


def extract_docx_media_jpeg(
    docx_path: str | Path,
    doc_id: str,
    media_ref: MediaRef,
    max_side: int = 1280,
    quality: int = 80,
) -> Path | None:
    """Lazily extract a single image from .docx, convert (.png/.tiff/.jpeg) to compressed RGB JPEG, and cache it."""
    ensure_data_dirs()
    out_dir = MEDIA_CACHE_DIR / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{media_ref.media_id}_{max_side}.jpg"
    if out_path.exists() and out_path.stat().st_size > 0:
        return out_path

    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            if media_ref.source_key not in zf.namelist():
                return None
            raw_bytes = zf.read(media_ref.source_key)

        with Image.open(io.BytesIO(raw_bytes)) as im:
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                bg = Image.new("RGB", im.size, (255, 255, 255))
                alpha = im.convert("RGBA")
                bg.paste(alpha, mask=alpha.split()[3])
                rgb = bg
            else:
                rgb = im.convert("RGB")

            w, h = rgb.size
            if max(w, h) > max_side:
                scale = max_side / float(max(w, h))
                rgb = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)

            rgb.save(out_path, format="JPEG", quality=quality, optimize=True)
        return out_path
    except Exception:
        return None
