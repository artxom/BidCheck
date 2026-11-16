"""Unified document loader, metadata/lot extractor, deterministic redline scanners, and hybrid section retriever."""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from backend.config import AST_CACHE_DIR, ensure_data_dirs
from backend.parsers.docx_parser import extract_docx_media_jpeg, parse_docx
from backend.parsers.models import (
    CURRENT_AST_VERSION,
    DeterministicFinding,
    DocumentAST,
    MediaRef,
    SectionNode,
)
from backend.parsers.pdf_parser import extract_pdf_media_jpeg, parse_pdf

PLACEHOLDER_PATTERNS = re.compile(
    r"(待补充|待填写|待提供|待完善|待确认|待更新|待粘贴|【待[^】]{0,8}】|\(待[^)]{0,8}\)|（待[^）]{0,8}）|TODO|TBD|XXXX+)",
    re.IGNORECASE,
)
COVER_KV_RE = re.compile(
    r"^(采购项目名称|项目名称|采购项目编号|项目编号|招标编号|分标号|标段号|标号|竞标人单位全称|投标人名称|供应商名称|竞标人地址|联系人|联系电话|授权代表)[^：:]*[：:]\s*(.*)$"
)
LOT_DEF_RE = re.compile(r"([A-Z0-9])\s*[标分][段包号]\s*[：:、—-]?\s*([^；;。，,\n]{2,28})")
TARGET_LOT_COVER_RE = re.compile(r"(?:分标号|标段号|标号|所投标段|标段)[：:\s]*([A-Z0-9]+)(?:\b|标|分|\s|$)")
OTHER_BUYER_SALUTATION_RE = re.compile(
    r"^\s*致\s*[：:]\s*([^\s：:，,。（(]{4,30}?(?:银行|分行|公司|局|中心|委员会|医院|大学|学院|集团))"
)

EXEMPT_CASE_KEYWORDS = ("业绩", "案例", "类似项目", "合同", "荣誉", "获奖", "简历", "证书", "著作权", "客户")
KEY_TABLE_SECTION_KEYWORDS = ("报价", "控股", "管理关系", "人员", "满足情况", "偏离", "授权", "业绩")
SEAL_REQUIRED_SECTIONS = ("磋商书", "投标函", "法定代表人身份证明", "授权书", "信用声明", "磋商报价表", "开标一览表")


def extract_media_jpeg(ast: DocumentAST, media_id: str, max_side: int = 1280, quality: int = 80) -> Path | None:
    media_ref: MediaRef | None = ast.media_index.get(media_id)
    if not media_ref:
        return None
    if ast.file_type == "docx":
        return extract_docx_media_jpeg(ast.source_path, ast.doc_id, media_ref, max_side=max_side, quality=quality)
    return extract_pdf_media_jpeg(ast.source_path, ast.doc_id, media_ref, max_side=max_side, quality=quality)


def extract_document_metadata(ast: DocumentAST) -> None:
    """Populate ast.metadata and ast.detected_lots from cover, filename, and early sections."""
    meta: dict[str, Any] = {}

    # Check filename for lot hints first (e.g. "标号：C" or "C标段")
    fn_lot = re.search(r"(?:标号|分标|标段)[：:\s]*([A-Z0-9])(?![A-Za-z0-9])", ast.filename)
    if not fn_lot:
        fn_lot = re.search(r"([A-Z])\s*[标分][段标包]", ast.filename)
    if fn_lot:
        meta["target_lot"] = fn_lot.group(1).upper()

    early_lines = list(ast.cover_lines)
    for sec in ast.sections[:8]:
        early_lines.append(sec.title)
        early_lines.extend(sec.paragraphs[:15])

    lots_map: dict[str, str] = {}
    for line in early_lines:
        m_kv = COVER_KV_RE.match(line.strip())
        if m_kv:
            key, val = m_kv.group(1), m_kv.group(2).strip().strip("_ ")
            if "名称" in key and "单位" not in key and "投标" not in key and "供应商" not in key and val:
                meta.setdefault("project_name", val)
            elif "编号" in key and val:
                meta.setdefault("project_code", val)
            elif key in ("分标号", "标段号", "标号") and val:
                m_c = re.match(r"^([A-Z0-9]+)", val.upper())
                if m_c:
                    meta["target_lot"] = m_c.group(1)
            elif ("单位全称" in key or "投标人" in key or "供应商" in key) and val:
                meta.setdefault("bidder_name", val)

        m_tlot = TARGET_LOT_COVER_RE.search(line)
        if m_tlot and ast.doc_role == "response":
            meta.setdefault("target_lot", m_tlot.group(1).upper())

        for m_lot in LOT_DEF_RE.finditer(line):
            lid = m_lot.group(1).upper()
            lname = m_lot.group(2).strip(" ：:()（）")
            if len(lname) >= 2 and lid not in lots_map:
                lots_map[lid] = f"{lid}标段：{lname}"

    # Scan section titles for lot definitions as well (critical for multi-lot tender docs)
    for sec in ast.sections:
        m_sec_lot = LOT_DEF_RE.match(sec.title)
        if m_sec_lot:
            lid = m_sec_lot.group(1).upper()
            lname = re.sub(r"(功能需求满足情况表|评分表)$", "", m_sec_lot.group(2)).strip(" ：:()（）")
            if len(lname) >= 2 and lid not in lots_map:
                lots_map[lid] = f"{lid}标段：{lname}"

    # Infer buyer name from project_name or filename (e.g. "广西北部湾银行大模型应用场景项目" -> "广西北部湾银行")
    proj_source = meta.get("project_name") or ast.filename
    m_buyer = re.match(r"^([\u4e00-\u9fa5]{3,20}?(?:银行|分行|有限责任公司|股份有限公司|集团|公司|局|中心|医院|大学))", proj_source)
    if m_buyer:
        meta["buyer_name"] = m_buyer.group(1)

    if not meta.get("project_code"):
        m_code = re.search(r"[（(](\d{6,14})[)）]", ast.filename)
        if m_code:
            meta["project_code"] = m_code.group(1)

    ast.detected_lots = [lots_map[k] for k in sorted(lots_map.keys())]
    ast.metadata = meta


def run_deterministic_scanners(
    response_ast: DocumentAST,
    tender_ast: DocumentAST | None = None,
) -> list[DeterministicFinding]:
    """Zero-token built-in capability scanners for formal redlines, blanks, consistency & seal slots."""
    findings: list[DeterministicFinding] = []
    f_counter = 0

    def _add(
        rule_type: str,
        severity: str,
        title: str,
        detail: str,
        sec: SectionNode | None = None,
        snippet: str = "",
    ) -> None:
        nonlocal f_counter
        f_counter += 1
        findings.append(
            DeterministicFinding(
                finding_id=f"det_{f_counter:03d}",
                rule_type=rule_type,  # type: ignore[arg-type]
                severity=severity,  # type: ignore[arg-type]
                title=title,
                detail=detail,
                section_id=sec.section_id if sec else "sec_0000",
                breadcrumb=sec.breadcrumb if sec else "封面与前导页",
                page_hint=sec.page_label if sec else "P1",
                snippet=snippet[:220],
            )
        )

    # 1. Cover unfilled fields check
    cover_sec = response_ast.sections[0] if response_ast.sections else None
    for line in response_ast.cover_lines:
        m_kv = COVER_KV_RE.match(line.strip())
        if m_kv:
            field_name, val = m_kv.group(1), m_kv.group(2).strip().strip("_")
            if not val:
                _add(
                    "cover_blank",
                    "fatal" if field_name in ("采购项目名称", "采购项目编号", "分标号", "竞标人单位全称") else "warning",
                    f"封面字段「{field_name}」留空未填",
                    f"响应文件封面检测到关键字段「{field_name}」后无内容，封标前必须补齐。",
                    cover_sec,
                    line,
                )

    # Build parent set to identify leaf sections accurately
    parent_ids = {s.parent_id for s in response_ast.sections if s.parent_id}

    # Determine expected buyer & target lot from tender + response metadata
    expected_buyer = (
        (tender_ast.metadata.get("buyer_name") if tender_ast else None)
        or response_ast.metadata.get("buyer_name")
        or ""
    )
    expected_code = (
        (tender_ast.metadata.get("project_code") if tender_ast else None)
        or response_ast.metadata.get("project_code")
        or ""
    )
    target_lot = response_ast.metadata.get("target_lot", "")
    other_lot_markers: list[tuple[str, str]] = []
    if tender_ast and target_lot:
        for lot_desc in tender_ast.detected_lots:
            m_l = re.match(r"^([A-Z0-9]+)标段[：:]*(.*)$", lot_desc)
            if m_l and m_l.group(1) != target_lot:
                other_lot_markers.append((f"{m_l.group(1)}标段", m_l.group(2).strip()))

    # 2. Check headers & footers for wrong buyer / placeholder
    for hf in response_ast.headers_footers:
        if PLACEHOLDER_PATTERNS.search(hf):
            _add("placeholder_text", "warning", "页眉/页脚存在待补充占位符", f"页眉页脚包含未清理占位文字：{hf}", cover_sec, hf)
        if expected_buyer:
            m_other = re.search(r"([\u4e00-\u9fa5]{2,14}银行)", hf)
            if m_other and m_other.group(1) not in expected_buyer and expected_buyer not in m_other.group(1):
                _add(
                    "wrong_entity_or_lot",
                    "fatal",
                    f"页眉/页脚疑似残留其他采购人名称「{m_other.group(1)}」",
                    f"目标采购人为「{expected_buyer}」，但页眉/页脚出现「{m_other.group(1)}」，存在严重串标废标风险。",
                    cover_sec,
                    hf,
                )

    # 3. Walk all sections for placeholders, empty leaf sections, empty key tables, wrong buyer/lot, and seal slots
    for sec in response_ast.sections:
        is_exempt_case = any(kw in sec.breadcrumb for kw in EXEMPT_CASE_KEYWORDS)

        # 3a. Placeholder in section title
        m_ph_title = PLACEHOLDER_PATTERNS.search(sec.title)
        if m_ph_title:
            _add(
                "placeholder_text",
                "fatal" if any(k in sec.title for k in ("报价", "磋商书", "授权", "控股", "资格")) else "warning",
                f"章节标题标记「{m_ph_title.group(0)}」：{sec.title}",
                f"章节「{sec.breadcrumb}」（{sec.page_label}）仍处于未完成占位状态。",
                sec,
                sec.title,
            )

        # 3b. Placeholder in paragraphs
        ph_hits_in_sec = 0
        for p_txt in sec.paragraphs:
            m_ph = PLACEHOLDER_PATTERNS.search(p_txt)
            if m_ph and ph_hits_in_sec < 2:
                ph_hits_in_sec += 1
                _add(
                    "placeholder_text",
                    "warning",
                    f"正文存在未完成占位符「{m_ph.group(0)}」",
                    f"在「{sec.breadcrumb}」（{sec.page_label}）正文中发现待补充标记。",
                    sec,
                    p_txt,
                )

            # Check salutation "致：XXX" for wrong buyer name!
            if not is_exempt_case and expected_buyer:
                for m_sal in OTHER_BUYER_SALUTATION_RE.finditer(p_txt):
                    sal_entity = m_sal.group(1)
                    if (
                        expected_buyer not in sal_entity
                        and sal_entity not in expected_buyer
                        and "代理" not in sal_entity
                        and "咨询" not in sal_entity
                    ):
                        _add(
                            "wrong_entity_or_lot",
                            "fatal",
                            f"函件抬头疑似写错采购人：「{sal_entity}」",
                            f"当前采购人为「{expected_buyer}」，但在「{sec.breadcrumb}」发现抬头「致：{sal_entity}」，极易导致直接废标！",
                            sec,
                            p_txt,
                        )

            # Check accidental cross-lot leakage (e.g. writing A标段 反洗钱助手 in C标段 proposal)
            if not is_exempt_case and other_lot_markers:
                for lot_code, lot_topic in other_lot_markers:
                    if lot_topic and len(lot_topic) >= 5 and lot_topic in p_txt and target_lot:
                        _add(
                            "wrong_entity_or_lot",
                            "warning",
                            f"疑似混入其他标段内容（{lot_code}：{lot_topic}）",
                            f"当前响应标段为 {target_lot}，但在「{sec.breadcrumb}」正文中出现其他标段专属名称「{lot_topic}」。",
                            sec,
                            p_txt,
                        )

        # 3c. Key Tables empty cells & placeholders
        is_key_table_sec = any(kw in sec.breadcrumb for kw in KEY_TABLE_SECTION_KEYWORDS)
        for tbl in sec.tables:
            m_tbl_ph = PLACEHOLDER_PATTERNS.search(tbl.markdown)
            if m_tbl_ph:
                _add(
                    "placeholder_text",
                    "fatal" if "报价" in sec.breadcrumb else "warning",
                    f"表格内含占位符「{m_tbl_ph.group(0)}」",
                    f"「{sec.breadcrumb}」（{sec.page_label}）表格 {tbl.table_id} 内存在未定稿内容。",
                    sec,
                    tbl.markdown[:200],
                )
            if is_key_table_sec and tbl.empty_cells:
                sample_cols = "、".join(sorted({ec.col_header for ec in tbl.empty_cells[:5] if ec.col_header}))
                _add(
                    "empty_table_cell",
                    "fatal" if any(k in sec.breadcrumb for k in ("报价", "满足情况")) else "warning",
                    f"关键响应表格存在 {len(tbl.empty_cells)} 处空白单元格",
                    f"「{sec.breadcrumb}」（{sec.page_label}）表格中列【{sample_cols or '必填项'}】存在留空单元格，请核查是否漏填。",
                    sec,
                    f"示例空行上下文：{tbl.empty_cells[0].row_context}",
                )

        # 3d. Empty leaf section check (no text, no tables, no images, and no child sections)
        all_tbl_imgs = sum(len(t.media_ids) for t in sec.tables)
        if (
            sec.level >= 1
            and sec.section_id not in parent_ids
            and len(sec.paragraphs) == 0
            and len(sec.tables) == 0
            and len(sec.media_ids) == 0
            and all_tbl_imgs == 0
        ):
            _add(
                "empty_section",
                "fatal" if any(k in sec.breadcrumb for k in ("报价", "资格", "授权", "磋商书", "信用")) else "warning",
                f"空章节无实质响应内容：{sec.title}",
                f"章节「{sec.breadcrumb}」（{sec.page_label}）标题下既无正文表格，也无内嵌扫描件图片。",
                sec,
                sec.title,
            )

        # 3e. Signature & seal slot check on formal declaration templates
        if sec.level == 1 and any(sk in sec.title for sk in SEAL_REQUIRED_SECTIONS):
            joined = " ".join(sec.paragraphs) + " " + " ".join(t.markdown for t in sec.tables)
            has_seal_anchor = any(w in joined for w in ("盖章", "公章", "签章", "签字"))
            total_sec_imgs = len(sec.media_ids) + all_tbl_imgs
            if not has_seal_anchor and len(joined.strip()) > 10:
                _add(
                    "seal_signature_slot",
                    "warning",
                    f"「{sec.title}」未检测到签字/盖章落款字样",
                    f"标准格式文书「{sec.title}」（{sec.page_label}）未见“盖章/签字”预留落款行，请核对第四章格式要求。",
                    sec,
                    joined[-160:],
                )
            elif has_seal_anchor and total_sec_imgs == 0 and "身份证明" not in sec.title:
                _add(
                    "seal_signature_slot",
                    "info",
                    f"「{sec.title}」已预留落款位（电子版未嵌印章图，请确认线下实体盖章或电子签章）",
                    f"文书「{sec.title}」（{sec.page_label}）落款结构存在，当前 Word 内无嵌入章图，出标封装/导出前请确保完成签章。",
                    sec,
                    joined[-140:],
                )

    # Check project code consistency if expected_code exists
    if expected_code and response_ast.cover_lines:
        cover_joined = " ".join(response_ast.cover_lines)
        if expected_code not in cover_joined:
            _add(
                "wrong_entity_or_lot",
                "fatal",
                f"响应文件封面未找到招标项目编号「{expected_code}」",
                f"招标文件项目编号为 {expected_code}，响应文件封面未匹配到该编号。",
                cover_sec,
                cover_joined[:180],
            )

    response_ast.deterministic_findings = findings
    return findings


def _tokenize_cn(text: str) -> list[str]:
    """Fast hybrid tokenizer producing Chinese character bigrams + English/number tokens."""
    cleaned = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9]+", " ", text.lower())
    tokens: list[str] = []
    for chunk in cleaned.split():
        if re.match(r"^[a-z0-9]+$", chunk):
            if len(chunk) >= 2:
                tokens.append(chunk)
        else:
            # Extract ASCII runs + Chinese 2-grams
            for asc in re.findall(r"[a-z0-9]{2,}", chunk):
                tokens.append(asc)
            cn_only = re.sub(r"[^\u4e00-\u9fa5]", "", chunk)
            if len(cn_only) == 1:
                tokens.append(cn_only)
            else:
                for i in range(len(cn_only) - 1):
                    tokens.append(cn_only[i : i + 2])
    return tokens


class SectionRetriever:
    """BM25-style + Hierarchical Heading Boost retriever over DocumentAST sections."""

    def __init__(self, ast: DocumentAST) -> None:
        self.ast = ast
        self.sec_by_id: dict[str, SectionNode] = {s.section_id: s for s in ast.sections}
        self.children_by_parent: dict[str, list[str]] = {}
        for s in ast.sections:
            if s.parent_id:
                self.children_by_parent.setdefault(s.parent_id, []).append(s.section_id)

        self.title_tf: dict[str, Counter[str]] = {}
        self.body_tf: dict[str, Counter[str]] = {}
        self.df: Counter[str] = Counter()
        self.N = max(1, len(ast.sections))

        for s in ast.sections:
            t_toks = _tokenize_cn(s.breadcrumb + " " + s.title)
            body_sample = "\n".join(s.paragraphs[:60]) + "\n" + "\n".join(t.markdown[:1200] for t in s.tables[:5])
            b_toks = _tokenize_cn(body_sample)
            self.title_tf[s.section_id] = Counter(t_toks)
            self.body_tf[s.section_id] = Counter(b_toks)
            for tok in set(t_toks) | set(b_toks):
                self.df[tok] += 1

    def search(
        self,
        query: str,
        keywords: list[str] | None = None,
        top_k: int = 6,
    ) -> list[SectionNode]:
        kw_str = " ".join(keywords or [])
        q_tokens = _tokenize_cn(f"{query} {kw_str}")
        if not q_tokens:
            return self.ast.sections[:top_k]

        q_counts = Counter(q_tokens)
        exact_phrases = [k.strip().lower() for k in (keywords or []) if len(k.strip()) >= 2]
        scores: list[tuple[float, SectionNode]] = []

        for s in self.ast.sections:
            sid = s.section_id
            t_tf = self.title_tf[sid]
            b_tf = self.body_tf[sid]
            score = 0.0
            for tok, qf in q_counts.items():
                df_val = self.df.get(tok, 0)
                if df_val == 0:
                    continue
                idf = math.log(1.0 + (self.N - df_val + 0.5) / (df_val + 0.5))
                # Strong boost on title/breadcrumb match
                if tok in t_tf:
                    score += idf * (3.5 * min(3, t_tf[tok])) * math.sqrt(qf)
                if tok in b_tf:
                    score += idf * (1.0 * min(4, math.log1p(b_tf[tok]))) * math.sqrt(qf)

            bc_lower = s.breadcrumb.lower()
            for ph in exact_phrases:
                if ph in bc_lower:
                    score += 12.0

            if score > 0:
                scores.append((score, s))

        scores.sort(key=lambda x: x[0], reverse=True)
        selected: list[SectionNode] = []
        seen_ids: set[str] = set()

        for _, sec in scores:
            if sec.section_id not in seen_ids:
                selected.append(sec)
                seen_ids.add(sec.section_id)
            # If matched section is a container parent (e.g. "7.2 资质证明文件") with little direct text, pull its direct children too!
            if len(sec.paragraphs) == 0 and len(sec.tables) == 0 and sec.section_id in self.children_by_parent:
                for cid in self.children_by_parent[sec.section_id][:12]:
                    if cid not in seen_ids and len(selected) < top_k + 6:
                        selected.append(self.sec_by_id[cid])
                        seen_ids.add(cid)
            if len(selected) >= top_k:
                break

        return selected


def build_tender_digest(tender_ast: DocumentAST, target_lot: str | None = None) -> str:
    """Build a comprehensive, lot-filtered structured text of the Tender Document for Master Agent planning.

    Skips lengthy contract boilerplate (Chapter 5 '合同格式') unless short, and filters out non-target lot sections/tables!
    """
    other_lot_prefixes: set[str] = set()
    if target_lot and tender_ast.detected_lots:
        for ld in tender_ast.detected_lots:
            m = re.match(r"^([A-Z0-9]+)标段", ld)
            if m and m.group(1).upper() != target_lot.upper():
                other_lot_prefixes.add(f"{m.group(1).upper()}标段")
                other_lot_prefixes.add(f"标段{m.group(1).upper()}")

    chunks: list[str] = []
    for sec in tender_ast.sections:
        # Skip non-target lot sections (e.g. skip A标段/B标段/D标段 when bidding C标段!)
        if other_lot_prefixes and any(op in sec.breadcrumb for op in other_lot_prefixes):
            continue
        # Compress Chapter 5 contract boilerplate to headings only (not bid response checklist items)
        if "第五章" in sec.breadcrumb and "合同" in sec.breadcrumb:
            continue

        sec_lines = [f"\n### [{sec.section_id} | {sec.page_label}] {sec.breadcrumb}"]
        if sec.paragraphs:
            p_joined = "\n".join(sec.paragraphs)
            sec_lines.append(p_joined[:8500])
        for tbl in sec.tables:
            sec_lines.append(f"\n[表格 {tbl.table_id} ({tbl.row_count}行×{tbl.col_count}列)]:\n{tbl.markdown[:8500]}")
        chunks.append("\n".join(sec_lines))

    full_text = "\n".join(chunks)
    # Cap around 55,000 chars so it stays lean yet preserves full Chapter 3 & 4 requirements
    return full_text[:55000]


def build_response_outline_summary(response_ast: DocumentAST, compact: bool = True) -> str:
    """Build a full-document outline map of the Bid Response Document (compact skeleton by default)."""
    lines: list[str] = []

    def _stats(sec: SectionNode) -> tuple[str, int]:
        tbl_img_cnt = sum(len(t.media_ids) for t in sec.tables)
        img_total = len(sec.media_ids) + tbl_img_cnt
        parts: list[str] = []
        if sec.char_count:
            parts.append(f"{sec.char_count}字")
        if sec.tables:
            parts.append(f"{len(sec.tables)}表")
        if img_total:
            parts.append(f"{img_total}图")
        return (" / ".join(parts) if parts else "空"), img_total

    if not compact:
        for sec in response_ast.sections:
            indent = "  " * max(0, sec.level - 1)
            stat_str, _ = _stats(sec)
            lines.append(f"{indent}- [{sec.section_id}] {sec.title} ({sec.page_label} | {stat_str})")
        return "\n".join(lines)

    sub_buf: list[SectionNode] = []

    def _flush_subs() -> None:
        if not sub_buf:
            return
        p_starts = [s.page_start for s in sub_buf if s.page_start]
        p_ends = [s.page_end for s in sub_buf if s.page_end]
        p_s = min(p_starts) if p_starts else None
        p_e = max(p_ends) if p_ends else p_s
        p_rng = f"P{p_s}-P{p_e}" if (p_s and p_e and p_s != p_e) else (f"P{p_s}" if p_s else "")

        tot_chars = sum(s.char_count for s in sub_buf)
        tot_tbls = sum(len(s.tables) for s in sub_buf)
        tot_imgs = sum(_stats(s)[1] for s in sub_buf)
        agg_parts: list[str] = []
        if tot_chars:
            agg_parts.append(f"{tot_chars}字")
        if tot_tbls:
            agg_parts.append(f"{tot_tbls}表")
        if tot_imgs:
            agg_parts.append(f"共{tot_imgs}图")
        agg_str = " / ".join(agg_parts) if agg_parts else "空"

        sample_names = "、".join(s.title[:20] for s in sub_buf[:3])
        if len(sub_buf) > 3:
            sample_names += "…"
        loc_meta = " | ".join(x for x in (p_rng, agg_str) if x)
        lines.append(f"    ↳ 子节×{len(sub_buf)} ({loc_meta}): {sample_names}")

        for sub in sub_buf:
            if PLACEHOLDER_PATTERNS.search(sub.title):
                sub_stat, _ = _stats(sub)
                lines.append(f"      - [{sub.section_id}] {sub.title} ({sub.page_label} | {sub_stat})")
        sub_buf.clear()

    for sec in response_ast.sections:
        if sec.level <= 2:
            _flush_subs()
            indent = "  " * max(0, sec.level - 1)
            stat_str, _ = _stats(sec)
            lines.append(f"{indent}- [{sec.section_id}] {sec.title} ({sec.page_label} | {stat_str})")
        else:
            sub_buf.append(sec)

    _flush_subs()
    return "\n".join(lines)


def parse_and_cache_document(
    file_path: str | Path,
    doc_role: str,
    doc_id: str,
    tender_ast_for_response: DocumentAST | None = None,
    force_reparse: bool = False,
) -> DocumentAST:
    """Parse .docx or .pdf into DocumentAST, run metadata + deterministic analysis, and cache JSON on disk."""
    ensure_data_dirs()
    cache_file = AST_CACHE_DIR / f"{doc_id}.json"
    path = Path(file_path)

    if cache_file.exists() and not force_reparse:
        try:
            ast = DocumentAST.model_validate_json(cache_file.read_text(encoding="utf-8"))
            if ast.ast_version == CURRENT_AST_VERSION:
                if doc_role == "response" and tender_ast_for_response is not None:
                    run_deterministic_scanners(ast, tender_ast_for_response)
                    cache_file.write_text(ast.model_dump_json(), encoding="utf-8")
                return ast
        except Exception:
            pass

    ext = path.suffix.lower()
    if ext == ".docx":
        ast = parse_docx(path, doc_role=doc_role, doc_id=doc_id)
    elif ext == ".pdf":
        ast = parse_pdf(path, doc_role=doc_role, doc_id=doc_id)
    else:
        raise ValueError(f"不支持的文件格式: {ext}（目前支持 .docx 与 .pdf，老旧 .doc 请先另存为 .docx）")

    extract_document_metadata(ast)
    if doc_role == "response":
        run_deterministic_scanners(ast, tender_ast_for_response)

    cache_file.write_text(ast.model_dump_json(), encoding="utf-8")
    return ast
