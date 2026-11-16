"""Concurrent sub-inspection worker engine combining built-in deterministic rules, text LLM, and on-demand Vision VLM."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from backend.db import get_project, upsert_checklist_item
from backend.llm.gateway import EVENT_BUS, LLM_GATEWAY
from backend.llm.prompts import TEXT_WORKER_SYSTEM_PROMPT, VISION_WORKER_SYSTEM_PROMPT
from backend.parsers.indexer import (
    SectionRetriever,
    build_response_outline_summary,
    extract_media_jpeg,
    parse_and_cache_document,
)
from backend.parsers.models import DeterministicFinding, DocumentAST, SectionNode
from backend.schemas import CATEGORY_LABELS, ChecklistItem, MatchedSectionRef


def _format_candidate_sections(
    sections: list[SectionNode],
    det_by_sec: dict[str, list[DeterministicFinding]],
) -> str:
    if not sections:
        return "（未检索到直接匹配的候选章节）"

    blocks: list[str] = []
    for sec in sections:
        tbl_imgs: list[str] = []
        for t in sec.tables:
            tbl_imgs.extend(t.media_ids)
        all_imgs = list(dict.fromkeys(sec.media_ids + tbl_imgs))

        header = (
            f"=== 章节 [{sec.section_id}] | 页码: {sec.page_label} | 路径: {sec.breadcrumb} "
            f"| 正文{len(sec.paragraphs)}段 / 表格{len(sec.tables)}个 / 内嵌图片{len(all_imgs)}张 ==="
        )
        parts = [header]

        sec_dets = det_by_sec.get(sec.section_id, [])
        if sec_dets:
            parts.append("【系统固有规则预警】:")
            for d in sec_dets:
                parts.append(f"  - [{d.severity.upper()}] {d.title}: {d.detail}")

        if sec.paragraphs:
            p_text = "\n".join(sec.paragraphs[:45])
            parts.append(f"【正文内容】:\n{p_text[:2800]}")

        for tbl in sec.tables[:4]:
            parts.append(f"【表格 {tbl.table_id} ({tbl.row_count}行×{tbl.col_count}列)】:\n{tbl.markdown[:2600]}")

        if all_imgs:
            parts.append(f"【章节内嵌扫描件/图片编号】: {', '.join(all_imgs[:15])} (共 {len(all_imgs)} 张)")

        blocks.append("\n".join(parts))

    return "\n\n".join(blocks)[:14000]


async def _inspect_single_item(
    project_id: str,
    item: ChecklistItem,
    response_ast: DocumentAST,
    retriever: SectionRetriever,
    outline_brief: str,
    det_by_sec: dict[str, list[DeterministicFinding]],
) -> ChecklistItem:
    t_start = time.perf_counter()
    item.run_status = "running"
    upsert_checklist_item(project_id, item)
    await EVENT_BUS.emit(project_id, "item_updated", item.model_dump())

    try:
        # Special handling for global formal redline item: combine deterministic scan results + cover/header check
        is_global_redline = (
            item.category == "format_redline"
            and any(k in item.title for k in ("全局形式红线", "封面与留空", "一致性与防串标"))
        )

        candidates = retriever.search(
            f"{item.title} {item.requirement_text}",
            keywords=item.search_keywords,
            top_k=7,
        )
        if is_global_redline and response_ast.sections:
            if response_ast.sections[0] not in candidates:
                candidates.insert(0, response_ast.sections[0])

        candidates_text = _format_candidate_sections(candidates, det_by_sec)
        global_det_summary = ""
        if is_global_redline and response_ast.deterministic_findings:
            lines = [
                f"- [{d.severity.upper()}] {d.page_hint} {d.breadcrumb}: {d.title} ({d.detail})"
                for d in response_ast.deterministic_findings[:25]
            ]
            global_det_summary = "\n\n【全篇确定性红线扫描汇总】:\n" + "\n".join(lines)

        user_prompt = (
            f"【检查项编号】: {item.item_id}\n"
            f"【所属维度】: {CATEGORY_LABELS.get(item.category, item.category)}\n"
            f"【检查项标题】: {item.title}\n"
            f"【招标要求详情】: {item.requirement_text}\n"
            f"【招标文件出处】: {item.tender_source or '招标文件要求'}\n"
            f"【是否要求图片/扫描件证明】: {'是' if item.requires_vision else '否'}\n\n"
            f"【我方响应文件候选章节内容】:\n{candidates_text}"
            f"{global_det_summary}\n\n"
            f"【响应文件章节目录速览（辅助确认是否存在其他命名章节）】:\n{outline_brief[:4500]}"
        )

        res_json, used_model, _ = await LLM_GATEWAY.chat_json(
            project_id=project_id,
            role="text_worker",
            system_prompt=TEXT_WORKER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=1200,
        )

        status_raw = str(res_json.get("compliance_status", "partial")).lower().strip()
        if status_raw not in ("passed", "partial", "missing"):
            status_raw = "partial"

        sec_by_id = {s.section_id: s for s in response_ast.sections}
        raw_matched_ids = res_json.get("matched_section_ids") or []
        matched_refs: list[MatchedSectionRef] = []
        collected_media_ids: list[str] = []

        for sid in raw_matched_ids:
            if isinstance(sid, str) and sid in sec_by_id:
                s_obj = sec_by_id[sid]
                matched_refs.append(
                    MatchedSectionRef(
                        section_id=s_obj.section_id,
                        breadcrumb=s_obj.breadcrumb,
                        page_label=s_obj.page_label,
                    )
                )
                collected_media_ids.extend(s_obj.media_ids)
                for tb in s_obj.tables:
                    collected_media_ids.extend(tb.media_ids)

        # Fallback matched_refs from top candidate if status != missing and LLM forgot section_id
        if not matched_refs and status_raw != "missing" and candidates:
            top_c = candidates[0]
            matched_refs.append(
                MatchedSectionRef(
                    section_id=top_c.section_id,
                    breadcrumb=top_c.breadcrumb,
                    page_label=top_c.page_label,
                )
            )
            for c_sec in candidates[:3]:
                collected_media_ids.extend(c_sec.media_ids)
                for tb in c_sec.tables:
                    collected_media_ids.extend(tb.media_ids)

        collected_media_ids = list(dict.fromkeys(collected_media_ids))[:12]

        # Enforce hard deterministic guard: if matched section has fatal placeholder (e.g. "待补充"), cannot be "passed"
        for mref in matched_refs:
            for d in det_by_sec.get(mref.section_id, []):
                if d.severity == "fatal" and d.rule_type in ("placeholder_text", "empty_section", "empty_table_cell"):
                    if status_raw == "passed":
                        status_raw = "partial"

        vision_verified = False
        vision_note = ""
        models_chain = [used_model]

        # On-demand multimodal verification ONLY for certificate/contract/ID/financial items
        if item.requires_vision and status_raw != "missing":
            if not collected_media_ids:
                # Check if candidates had images even if parent section_id was matched
                for c_sec in candidates[:4]:
                    collected_media_ids.extend(c_sec.media_ids)
                    for tb in c_sec.tables:
                        collected_media_ids.extend(tb.media_ids)
                collected_media_ids = list(dict.fromkeys(collected_media_ids))[:12]

            if not collected_media_ids:
                if status_raw == "passed":
                    status_raw = "partial"
                vision_note = "条款要求提供扫描件/图片证明，但对应章节未检测到内嵌图片。"
            elif LLM_GATEWAY.has_configured_key("vision_worker"):
                jpeg_paths: list[Path] = []
                for mid in collected_media_ids[:3]:
                    jp = await asyncio.to_thread(extract_media_jpeg, response_ast, mid, 1024, 78)
                    if jp and jp.exists():
                        jpeg_paths.append(jp)

                if jpeg_paths:
                    try:
                        v_prompt = (
                            f"【核验条款】: {item.title}\n"
                            f"【招标要求】: {item.requirement_text}\n"
                            f"【所在章节】: {' / '.join(m.breadcrumb for m in matched_refs[:2])}\n"
                            f"本章节共含 {len(collected_media_ids)} 张图，以下附前 {len(jpeg_paths)} 张代表性扫描图进行核验。"
                        )
                        v_res, v_model, _ = await LLM_GATEWAY.chat_json(
                            project_id=project_id,
                            role="vision_worker",
                            system_prompt=VISION_WORKER_SYSTEM_PROMPT,
                            user_prompt=v_prompt,
                            image_paths=jpeg_paths,
                            temperature=0.1,
                            max_tokens=500,
                        )
                        vision_verified = True
                        vision_note = str(v_res.get("vision_note", "")).strip()
                        downgrade = str(v_res.get("downgrade_to", "keep")).lower().strip()
                        if downgrade in ("partial", "missing") and status_raw == "passed":
                            status_raw = downgrade
                        if v_model not in models_chain:
                            models_chain.append(v_model)
                    except Exception as v_exc:
                        vision_note = f"已定位 {len(collected_media_ids)} 张扫描图（视觉模型跳过：{str(v_exc)[:45]}）"
            else:
                vision_note = f"已定位 {len(collected_media_ids)} 张内嵌扫描图（可在证据面板预览原图）"

        elapsed_sec = time.perf_counter() - t_start
        item.run_status = "completed"
        item.compliance_status = status_raw  # type: ignore[assignment]
        item.matched_sections = matched_refs
        item.evidence_excerpt = str(res_json.get("evidence_excerpt", "")).strip()
        item.media_ids = collected_media_ids
        item.vision_verified = vision_verified
        item.vision_note = vision_note
        item.conclusion = str(res_json.get("conclusion", "")).strip()
        item.remediation = str(res_json.get("remediation", "")).strip()
        item.checked_by_model = " + ".join(models_chain)
        item.duration_ms = int(elapsed_sec * 1000)

        EVENT_BUS.record_item_finished(project_id, elapsed_sec)
        upsert_checklist_item(project_id, item)
        await EVENT_BUS.emit(project_id, "item_updated", item.model_dump())
        return item

    except Exception as exc:
        elapsed_sec = time.perf_counter() - t_start
        item.run_status = "failed"
        item.conclusion = f"检查执行异常：{str(exc)[:160]}"
        item.duration_ms = int(elapsed_sec * 1000)
        upsert_checklist_item(project_id, item)
        await EVENT_BUS.emit(project_id, "item_updated", item.model_dump())
        return item


async def execute_inspection_workflow(project_id: str, recheck_only: bool = False) -> None:
    """Run all enabled checklist items concurrently, checkpointing each to SQLite, then assemble final report."""
    from backend.agents.report_agent import assemble_final_report

    proj = get_project(project_id)
    if not proj or not proj.response_doc or not proj.tender_doc:
        return

    tender_ast_path = proj.tender_doc.metadata.get("source_path", "")
    resp_ast_path = proj.response_doc.metadata.get("source_path", "")
    tender_ast = await asyncio.to_thread(
        parse_and_cache_document, tender_ast_path, "tender", proj.tender_doc.doc_id
    )
    response_ast = await asyncio.to_thread(
        parse_and_cache_document, resp_ast_path, "response", proj.response_doc.doc_id, tender_ast
    )

    enabled_items = [it for it in proj.checklist if it.enabled]
    for it in proj.checklist:
        if not it.enabled and it.run_status != "skipped":
            it.run_status = "skipped"
            upsert_checklist_item(project_id, it)

    if recheck_only:
        target_items = [
            it
            for it in enabled_items
            if it.run_status in ("pending", "failed") or it.compliance_status in ("unchecked", "partial", "missing")
        ]
    else:
        target_items = enabled_items
        for it in target_items:
            it.run_status = "pending"
            it.compliance_status = "unchecked"
            upsert_checklist_item(project_id, it)

    already_done = len(enabled_items) - len(target_items)
    total_enabled = len(enabled_items)

    EVENT_BUS.mark_run_started(project_id)
    await EVENT_BUS.sync_and_broadcast_telemetry(
        project_id,
        stage="inspecting",
        stage_label=f"核查中 0/{len(target_items)}" if recheck_only else f"核查中 {already_done}/{total_enabled}",
        completed_items=already_done,
        total_items=total_enabled,
    )

    retriever = await asyncio.to_thread(SectionRetriever, response_ast)
    outline_brief = await asyncio.to_thread(build_response_outline_summary, response_ast)
    det_by_sec: dict[str, list[DeterministicFinding]] = {}
    for df in response_ast.deterministic_findings:
        det_by_sec.setdefault(df.section_id, []).append(df)

    done_counter = [already_done]
    counter_lock = asyncio.Lock()

    async def _worker_wrapper(chk_item: ChecklistItem) -> None:
        await _inspect_single_item(
            project_id=project_id,
            item=chk_item,
            response_ast=response_ast,
            retriever=retriever,
            outline_brief=outline_brief,
            det_by_sec=det_by_sec,
        )
        async with counter_lock:
            done_counter[0] += 1
            await EVENT_BUS.sync_and_broadcast_telemetry(
                project_id,
                stage="inspecting",
                stage_label=f"核查中 {done_counter[0]}/{total_enabled}",
                completed_items=done_counter[0],
                total_items=total_enabled,
            )

    await asyncio.gather(*(_worker_wrapper(it) for it in target_items))

    # Assemble final report via Report Assembler Agent
    await assemble_final_report(project_id, response_ast)
