"""Standalone Single-File Interactive HTML Inspection Report Generator."""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import io
import json
import os
from pathlib import Path
import re
from typing import Any
import zipfile

from PIL import Image
import pymupdf as fitz

import backend.config as cfg
from backend.db import now_iso
from backend.parsers.indexer import parse_and_cache_document
from backend.parsers.models import DocumentAST, MediaRef
from backend.schemas import ProjectDetail

_CSS_HREF_RE = re.compile(r'<link[^>]+rel=["\']stylesheet["\'][^>]+href=["\']([^"\']+)["\']', re.I)
_JS_SRC_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\'][^>]*></script>', re.I)


def _read_frontend_bundle(dist_dir: Path) -> tuple[str, str]:
    """Read compiled CSS and JS assets from frontend/dist for inline single-file bundling."""
    index_path = dist_dir / "index.html"
    if not dist_dir.exists() or not index_path.exists():
        raise RuntimeError("前端静态产物尚未编译，无法导出交互式 HTML 报告。")

    root_resolved = dist_dir.resolve()
    index_html = index_path.read_text(encoding="utf-8")

    css_paths: list[Path] = []
    for href in _CSS_HREF_RE.findall(index_html):
        rel = href.lstrip("/")
        cand = (dist_dir / rel).resolve()
        if cand.is_file() and cand.is_relative_to(root_resolved):
            css_paths.append(cand)
    if not css_paths and (dist_dir / "assets").exists():
        css_paths = sorted((dist_dir / "assets").glob("*.css"))

    js_paths: list[Path] = []
    for src in _JS_SRC_RE.findall(index_html):
        rel = src.lstrip("/")
        cand = (dist_dir / rel).resolve()
        if cand.is_file() and cand.is_relative_to(root_resolved):
            js_paths.append(cand)
    if not js_paths and (dist_dir / "assets").exists():
        js_paths = sorted((dist_dir / "assets").glob("*.js"))

    if not css_paths or not js_paths:
        raise RuntimeError("前端编译产物缺失 CSS 或 JS 资源，请先构建前端。")

    css_text = "\n".join(p.read_text(encoding="utf-8") for p in css_paths)
    js_text = "\n".join(p.read_text(encoding="utf-8") for p in js_paths)
    return css_text, js_text


def _sanitize_project_dict(proj: ProjectDetail) -> dict[str, Any]:
    """Serialize ProjectDetail while stripping local filesystem paths."""
    data = proj.model_dump()
    for doc_key in ("tender_doc", "response_doc"):
        doc_obj = data.get(doc_key)
        if isinstance(doc_obj, dict) and isinstance(doc_obj.get("metadata"), dict):
            doc_obj["metadata"].pop("source_path", None)
    return data


def _load_response_ast(proj: ProjectDetail) -> DocumentAST | None:
    if not proj.response_doc:
        return None
    src = str(proj.response_doc.metadata.get("source_path", ""))
    if src and Path(src).exists():
        return parse_and_cache_document(src, "response", proj.response_doc.doc_id)

    cache_file = cfg.AST_CACHE_DIR / f"{proj.response_doc.doc_id}.json"
    if cache_file.exists():
        try:
            return DocumentAST.model_validate_json(cache_file.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _encode_image_bytes_to_webp(raw_bytes: bytes, max_side: int = 1000, quality: int = 70) -> bytes:
    """Convert raw image bytes to white-backed RGB WebP constrained by max_side."""
    try:
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
                rgb = rgb.resize(
                    (max(1, int(w * scale)), max(1, int(h * scale))),
                    Image.Resampling.LANCZOS,
                )

            buf = io.BytesIO()
            rgb.save(buf, format="WEBP", quality=quality, method=2)
            return buf.getvalue()
    except Exception:
        return b""


def _extract_all_media_webp(
    ast: DocumentAST,
    proj: ProjectDetail,
    max_side: int = 1000,
    quality: int = 70,
) -> tuple[dict[str, str], dict[str, str]]:
    ordered_mids: list[str] = []
    seen_mids: set[str] = set()

    for sec in ast.sections:
        for mid in sec.media_ids:
            if mid not in seen_mids and mid in ast.media_index:
                seen_mids.add(mid)
                ordered_mids.append(mid)
        for tbl in sec.tables:
            for mid in tbl.media_ids:
                if mid not in seen_mids and mid in ast.media_index:
                    seen_mids.add(mid)
                    ordered_mids.append(mid)

    for it in proj.checklist:
        for mid in it.media_ids:
            if mid not in seen_mids and mid in ast.media_index:
                seen_mids.add(mid)
                ordered_mids.append(mid)

    if not ordered_mids:
        return {}, {}

    cfg.ensure_data_dirs()
    cache_dir = cfg.MEDIA_CACHE_DIR / ast.doc_id
    cache_dir.mkdir(parents=True, exist_ok=True)

    source_to_blob: dict[str, str] = {}
    blob_to_ref: dict[str, MediaRef] = {}
    blob_to_mids: dict[str, list[str]] = {}
    media_map: dict[str, str] = {}

    for mid in ordered_mids:
        mref = ast.media_index[mid]
        dedup_key = mref.source_key or mid
        blob_key = source_to_blob.get(dedup_key)
        if blob_key is None:
            blob_key = f"b_{len(source_to_blob) + 1:04d}"
            source_to_blob[dedup_key] = blob_key
            blob_to_ref[blob_key] = mref
            blob_to_mids[blob_key] = []
        media_map[mid] = blob_key
        blob_to_mids[blob_key].append(mid)

    webp_bytes_by_blob: dict[str, bytes] = {}
    pending_refs: dict[str, MediaRef] = {}

    for blob_key, mref in blob_to_ref.items():
        dedup_key = mref.source_key or mref.media_id
        digest = hashlib.sha1(dedup_key.encode("utf-8")).hexdigest()[:16]
        cache_path = cache_dir / f"snap_{digest}_{max_side}.webp"
        if cache_path.exists() and cache_path.stat().st_size > 0:
            webp_bytes_by_blob[blob_key] = cache_path.read_bytes()
        else:
            pending_refs[blob_key] = mref

    if pending_refs:
        raw_jobs: list[tuple[str, bytes, Path]] = []
        src_path = Path(ast.source_path) if ast.source_path else None

        if ast.file_type == "docx" and src_path and src_path.exists():
            try:
                with zipfile.ZipFile(src_path, "r") as zf:
                    names = set(zf.namelist())
                    for blob_key, mref in pending_refs.items():
                        if mref.source_key in names:
                            dedup_key = mref.source_key or mref.media_id
                            digest = hashlib.sha1(dedup_key.encode("utf-8")).hexdigest()[:16]
                            cache_path = cache_dir / f"snap_{digest}_{max_side}.webp"
                            raw_jobs.append((blob_key, zf.read(mref.source_key), cache_path))
            except Exception:
                pass
        elif ast.file_type == "pdf" and src_path and src_path.exists():
            try:
                pdf_doc = fitz.open(src_path)
                try:
                    for blob_key, mref in pending_refs.items():
                        try:
                            parts = mref.source_key.split(":")
                            xref = int(parts[2]) if len(parts) >= 3 else int(mref.rel_id)
                            base_img = pdf_doc.extract_image(xref)
                            raw_bytes = base_img.get("image", b"")
                            if raw_bytes:
                                dedup_key = mref.source_key or mref.media_id
                                digest = hashlib.sha1(dedup_key.encode("utf-8")).hexdigest()[:16]
                                cache_path = cache_dir / f"snap_{digest}_{max_side}.webp"
                                raw_jobs.append((blob_key, raw_bytes, cache_path))
                        except Exception:
                            continue
                finally:
                    pdf_doc.close()
            except Exception:
                pass

        # Fallback: check previously cached JPEGs if source document is unavailable
        queued_keys = {job[0] for job in raw_jobs}
        for blob_key, mref in pending_refs.items():
            if blob_key in queued_keys:
                continue
            for mid in blob_to_mids.get(blob_key, []):
                jpg_matches = sorted(cache_dir.glob(f"{mid}_*.jpg"), reverse=True)
                if jpg_matches and jpg_matches[0].stat().st_size > 0:
                    dedup_key = mref.source_key or mref.media_id
                    digest = hashlib.sha1(dedup_key.encode("utf-8")).hexdigest()[:16]
                    cache_path = cache_dir / f"snap_{digest}_{max_side}.webp"
                    raw_jobs.append((blob_key, jpg_matches[0].read_bytes(), cache_path))
                    break

        if raw_jobs:
            def _convert(job: tuple[str, bytes, Path]) -> tuple[str, bytes]:
                b_key, raw, c_path = job
                encoded = _encode_image_bytes_to_webp(raw, max_side=max_side, quality=quality)
                if encoded:
                    try:
                        c_path.write_bytes(encoded)
                    except OSError:
                        pass
                return b_key, encoded

            workers = min(8, os.cpu_count() or 4, len(raw_jobs))
            with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
                for b_key, encoded in pool.map(_convert, raw_jobs):
                    if encoded:
                        webp_bytes_by_blob[b_key] = encoded

    media_blobs: dict[str, str] = {}
    for blob_key, webp_bytes in webp_bytes_by_blob.items():
        if webp_bytes:
            b64 = base64.b64encode(webp_bytes).decode("ascii")
            media_blobs[blob_key] = f"data:image/webp;base64,{b64}"

    clean_media_map = {mid: b_key for mid, b_key in media_map.items() if b_key in media_blobs}
    return clean_media_map, media_blobs


def _escape_json_for_html_script(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def build_html_report(
    proj: ProjectDetail,
    frontend_dist_dir: Path | None = None,
) -> Path:
    """Generate a self-contained interactive static HTML inspection report matching the workbench UI."""
    cfg.ensure_data_dirs()
    out_path = cfg.REPORTS_DIR / f"{proj.id}_report.html"

    dist_dir = frontend_dist_dir or cfg.FRONTEND_DIST_DIR
    css_text, js_text = _read_frontend_bundle(dist_dir)

    response_ast = _load_response_ast(proj)
    outline: list[dict[str, Any]] = []
    sections_map: dict[str, dict[str, Any]] = {}
    deterministic_findings: list[dict[str, Any]] = []
    media_map: dict[str, str] = {}
    media_blobs: dict[str, str] = {}

    if response_ast is not None:
        deterministic_findings = [d.model_dump() for d in response_ast.deterministic_findings]
        det_by_sec: dict[str, list[dict[str, Any]]] = {}
        for d in response_ast.deterministic_findings:
            det_by_sec.setdefault(d.section_id, []).append(d.model_dump())

        for sec in response_ast.sections:
            all_imgs = list(
                dict.fromkeys(sec.media_ids + [mid for t in sec.tables for mid in t.media_ids])
            )
            outline.append(
                {
                    "section_id": sec.section_id,
                    "level": sec.level,
                    "title": sec.title,
                    "breadcrumb": sec.breadcrumb,
                    "page_label": sec.page_label,
                    "char_count": sec.char_count,
                    "table_count": len(sec.tables),
                    "image_count": len(all_imgs),
                }
            )
            sections_map[sec.section_id] = {
                "section_id": sec.section_id,
                "level": sec.level,
                "title": sec.title,
                "breadcrumb": sec.breadcrumb,
                "page_label": sec.page_label,
                "paragraphs": sec.paragraphs,
                "tables": [
                    {
                        "table_id": t.table_id,
                        "row_count": t.row_count,
                        "col_count": t.col_count,
                        "headers": t.headers,
                        "rows": t.rows,
                        "media_ids": t.media_ids,
                    }
                    for t in sec.tables
                ],
                "media_ids": all_imgs,
                "deterministic_findings": det_by_sec.get(sec.section_id, []),
            }

        media_map, media_blobs = _extract_all_media_webp(response_ast, proj)
    elif proj.report:
        deterministic_findings = [d.model_dump() for d in proj.report.deterministic_findings]

    snapshot = {
        "format": "bidguard-static-report-v1",
        "exported_at": now_iso()[:16].replace("T", " "),
        "app_version": cfg.APP_VERSION,
        "project": _sanitize_project_dict(proj),
        "outline": outline,
        "deterministic_findings": deterministic_findings,
        "sections": sections_map,
        "media_map": media_map,
        "media_blobs": media_blobs,
    }

    safe_title = html.escape(f"{proj.name or '标书智检'} - 标书检查报告")
    safe_css = re.sub(r"</style", "<\\/style", css_text, flags=re.IGNORECASE)
    safe_js = re.sub(r"</script", "<\\/script", js_text, flags=re.IGNORECASE)
    safe_json = _escape_json_for_html_script(snapshot)

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{safe_title}</title>
    <script>
      (() => {{
        try {{
          const m = localStorage.getItem('bidguard-theme') || 'system';
          const d =
            m === 'dark' ||
            (m !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches);
          document.documentElement.classList.toggle('dark', d);
          document.documentElement.style.colorScheme = d ? 'dark' : 'light';
        }} catch {{}}
      }})();
    </script>
    <style>{safe_css}</style>
  </head>
  <body class="bg-[#F4F4F6] text-[#1D1D1F] dark:bg-[#161618] dark:text-[#F5F5F7] antialiased selection:bg-[#007AFF]/20 dark:selection:bg-[#0A84FF]/30">
    <div id="root"></div>
    <script id="bidguard-report-snapshot" type="application/json">{safe_json}</script>
    <script type="module">{safe_js}</script>
  </body>
</html>
"""
    out_path.write_text(html_doc, encoding="utf-8")
    return out_path
