"""Master Agent: single conversational entry point for 0-token precheck, tender planning, cancellation, and Q&A."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from backend.agents.worker_engine import execute_inspection_workflow
from backend.db import (
    append_message,
    get_project,
    get_settings,
    save_checklist,
    update_project_fields,
)
from backend.llm.gateway import EVENT_BUS, LLM_GATEWAY
from backend.llm.prompts import MASTER_CHAT_SYSTEM_PROMPT, MASTER_PLANNER_SYSTEM_PROMPT
from backend.parsers.indexer import (
    SectionRetriever,
    build_response_outline_summary,
    build_tender_digest,
    parse_and_cache_document,
)
from backend.parsers.models import DocumentAST
from backend.schemas import CATEGORY_LABELS, ChatMessage, ChecklistItem, ProjectDetail

_RUNNING_TASKS: dict[str, asyncio.Task[Any]] = {}


def is_project_running(project_id: str) -> bool:
    t = _RUNNING_TASKS.get(project_id)
    return bool(t and not t.done())


def _register_task(project_id: str, task: asyncio.Task[Any]) -> None:
    _RUNNING_TASKS[project_id] = task

    def _cleanup(done_t: asyncio.Task[Any]) -> None:
        if _RUNNING_TASKS.get(project_id) is done_t:
            _RUNNING_TASKS.pop(project_id, None)

    task.add_done_callback(_cleanup)


def launch_background_inspection(project_id: str, recheck_only: bool = False) -> bool:
    if is_project_running(project_id):
        return False
    task = asyncio.create_task(execute_inspection_workflow(project_id, recheck_only=recheck_only))
    _register_task(project_id, task)
    return True


async def _run_background_plan(project_id: str, target_lot_override: str | None = None) -> None:
    try:
        await generate_inspection_plan(project_id, target_lot_override=target_lot_override)
    except asyncio.CancelledError:
        return
    except Exception as exc:
        if get_project(project_id):
            err_msg = append_message(
                project_id,
                "assistant",
                f"生成检查计划时遇到异常：`{str(exc)[:240]}`",
                msg_type="error",
            )
            await EVENT_BUS.emit(project_id, "chat_message", err_msg.model_dump())


def launch_background_plan(project_id: str, target_lot_override: str | None = None) -> bool:
    if is_project_running(project_id):
        return False
    task = asyncio.create_task(_run_background_plan(project_id, target_lot_override=target_lot_override))
    _register_task(project_id, task)
    return True


async def cancel_project_task(project_id: str) -> bool:
    t = _RUNNING_TASKS.get(project_id)
    if not t or t.done():
        return False
    t.cancel()
    try:
        await t
    except (asyncio.CancelledError, Exception):
        pass
    if _RUNNING_TASKS.get(project_id) is t:
        _RUNNING_TASKS.pop(project_id, None)
    return True


def _load_response_ast_if_cached(proj: ProjectDetail | None) -> DocumentAST | None:
    if not proj or not proj.response_doc:
        return None
    src = str(proj.response_doc.metadata.get("source_path", ""))
    if not src or not Path(src).exists():
        return None
    try:
        return parse_and_cache_document(src, "response", proj.response_doc.doc_id)
    except Exception:
        return None


def _estimate_plan_metrics(
    items: list[ChecklistItem],
    response_ast: DocumentAST | None = None,
) -> tuple[int, float, int]:
    """Estimate pre-run tokens, CNY cost, and ETA from actual retrieved sections and role pricing."""
    settings = get_settings()
    enabled = [it for it in items if it.enabled]

    text_route = settings.routes.get("text_worker")
    vision_route = settings.routes.get("vision_worker")
    report_route = settings.routes.get("report_assembler")

    text_conc = max(1, text_route.concurrency if text_route else 6)
    vision_conc = max(1, vision_route.concurrency if vision_route else 3)
    vision_enabled = bool(vision_route and vision_route.enabled)

    text_in_tokens = 0
    text_out_tokens = 0
    vision_in_tokens = 0
    vision_out_tokens = 0
    vision_calls = 0

    if response_ast is not None and enabled:
        retriever = SectionRetriever(response_ast)
        outline_len = min(8000, len(build_response_outline_summary(response_ast, compact=True)))
        for it in enabled:
            candidates = retriever.search(
                f"{it.title} {it.requirement_text}",
                keywords=it.search_keywords,
                top_k=7,
            )
            cand_chars = min(14000, sum(min(5400, s.char_count) + 180 for s in candidates))
            prompt_chars = cand_chars + outline_len + 950
            text_in_tokens += int(prompt_chars * 0.68)
            text_out_tokens += 320

            if it.requires_vision and vision_enabled:
                c_mids: list[str] = []
                for c_sec in candidates[:4]:
                    c_mids.extend(c_sec.media_ids)
                    for tb in c_sec.tables:
                        c_mids.extend(tb.media_ids)
                img_cnt = min(3, max(1, len(set(c_mids))))
                vision_in_tokens += img_cnt * 780 + 350
                vision_out_tokens += 160
                vision_calls += 1
    else:
        text_in_tokens = len(enabled) * 4200
        text_out_tokens = len(enabled) * 320
        for it in enabled:
            if it.requires_vision and vision_enabled:
                vision_in_tokens += 2 * 780 + 350
                vision_out_tokens += 160
                vision_calls += 1

    report_in_tokens = len(enabled) * 140 + 1200 if enabled else 0
    report_out_tokens = 700 if enabled else 0

    t_in_p = text_route.input_price_per_m if text_route else 0.8
    t_out_p = text_route.output_price_per_m if text_route else 2.0
    v_in_p = vision_route.input_price_per_m if vision_route else 1.5
    v_out_p = vision_route.output_price_per_m if vision_route else 4.5
    r_in_p = report_route.input_price_per_m if report_route else 2.4
    r_out_p = report_route.output_price_per_m if report_route else 9.6

    est_cost = (
        text_in_tokens * t_in_p
        + text_out_tokens * t_out_p
        + vision_in_tokens * v_in_p
        + vision_out_tokens * v_out_p
        + report_in_tokens * r_in_p
        + report_out_tokens * r_out_p
    ) / 1_000_000.0

    est_tokens = (
        text_in_tokens
        + text_out_tokens
        + vision_in_tokens
        + vision_out_tokens
        + report_in_tokens
        + report_out_tokens
    )
    est_sec = int((len(enabled) * 4.8) / text_conc + (vision_calls * 5.0) / vision_conc + 7)
    return est_tokens, round(est_cost, 3), max(8, est_sec)


async def emit_document_precheck(
    project_id: str,
    tender_ast: DocumentAST,
    response_ast: DocumentAST,
) -> ChatMessage:
    """Emit a 0-token local precheck card after both documents are mounted and await user confirmation."""
    proj = get_project(project_id)
    detected_lot = response_ast.metadata.get("target_lot", "") or (proj.target_lot if proj else "")
    proj_title = tender_ast.metadata.get("project_name") or (proj.name if proj else "新建项目")
    if detected_lot and f"{detected_lot}标" not in proj_title:
        proj_title = f"{proj_title}（{detected_lot}标段）"

    tender_digest = await asyncio.to_thread(build_tender_digest, tender_ast, detected_lot or None)
    resp_outline = await asyncio.to_thread(build_response_outline_summary, response_ast, True)
    est_plan_input_tokens = max(
        1000, int((len(tender_digest) + len(resp_outline) + 1400) * 0.6)
    )

    update_project_fields(
        project_id,
        name=proj_title[:60],
        target_lot=detected_lot,
        stage="idle",
    )
    await EVENT_BUS.sync_and_broadcast_telemetry(
        project_id,
        stage="idle",
        stage_label="待生成清单",
    )

    det_cnt = len(response_ast.deterministic_findings)
    lot_info = f"**{detected_lot}标段**" if detected_lot else "单标段"
    lots_str = ", ".join(tender_ast.detected_lots) if tender_ast.detected_lots else "单标段"
    has_key = LLM_GATEWAY.has_configured_key("master")

    lines = [
        "**文档预检完成**",
        f"- 招标：`{tender_ast.total_pages}` 页 · `{len(tender_ast.sections)}` 节（{lots_str}）",
        f"- 响应：`{response_ast.total_pages}` 页 · `{response_ast.total_images}` 图 · {lot_info} · 形式预警 `{det_cnt}` 处",
        f"- 规划输入预估：`~{max(1, round(est_plan_input_tokens / 1000))}k` Tokens（未调用大模型）",
    ]
    if not has_key:
        lines.append("\n请先配置 API Key（`⌘,`）。")

    msg = append_message(
        project_id,
        role="assistant",
        content="\n".join(lines),
        msg_type="precheck_card",
        meta={
            "detected_lots": tender_ast.detected_lots,
            "target_lot": detected_lot,
            "est_plan_input_tokens": est_plan_input_tokens,
            "deterministic_count": det_cnt,
        },
    )
    await EVENT_BUS.emit(project_id, "chat_message", msg.model_dump())
    return msg


async def generate_inspection_plan(
    project_id: str,
    target_lot_override: str | None = None,
) -> ChatMessage:
    """Analyze attached Tender + Response ASTs, extract target lot & full checklist via Master Agent, and await confirm."""
    proj = get_project(project_id)
    if not proj or not proj.tender_doc or not proj.response_doc:
        raise ValueError("请先挂载《官方招标文件》与《我方响应文件》后再生成检查计划。")

    current_task = asyncio.current_task()
    existing_task = _RUNNING_TASKS.get(project_id)
    if existing_task and not existing_task.done() and existing_task is not current_task:
        raise RuntimeError("当前已有任务正在运行中，请等待或先停止当前任务。")
    if current_task and existing_task is not current_task:
        _register_task(project_id, current_task)

    tender_ast = await asyncio.to_thread(
        parse_and_cache_document,
        proj.tender_doc.metadata.get("source_path", ""),
        "tender",
        proj.tender_doc.doc_id,
    )
    response_ast = await asyncio.to_thread(
        parse_and_cache_document,
        proj.response_doc.metadata.get("source_path", ""),
        "response",
        proj.response_doc.doc_id,
        tender_ast,
    )

    detected_lot = (
        (target_lot_override or "").strip().upper()
        or response_ast.metadata.get("target_lot", "")
        or proj.target_lot
    )

    if not LLM_GATEWAY.has_configured_key("master"):
        if current_task and _RUNNING_TASKS.get(project_id) is current_task:
            _RUNNING_TASKS.pop(project_id, None)
        return await emit_document_precheck(project_id, tender_ast, response_ast)

    EVENT_BUS.mark_run_started(project_id)
    await EVENT_BUS.sync_and_broadcast_telemetry(
        project_id,
        stage="planning",
        stage_label="规划中",
    )

    async def _planning_heartbeat() -> None:
        while True:
            await asyncio.sleep(1.0)
            await EVENT_BUS.sync_and_broadcast_telemetry(project_id)

    heartbeat_task = asyncio.create_task(_planning_heartbeat())

    try:
        tender_digest = await asyncio.to_thread(build_tender_digest, tender_ast, detected_lot or None)
        resp_outline = await asyncio.to_thread(build_response_outline_summary, response_ast, True)

        planner_user_prompt = (
            f"【识别上下文】\n"
            f"- 招标文件名称：{tender_ast.filename}\n"
            f"- 招标文件包含标段：{', '.join(tender_ast.detected_lots) if tender_ast.detected_lots else '不区分标段'}\n"
            f"- 我方响应文件名称：{response_ast.filename}\n"
            f"- 自动检测/指定的我方所投标段：{detected_lot or '请根据响应文件封面与目录判断'}\n\n"
            f"【官方招标/采购文件核心内容（已过滤非目标标段与合同样板）】:\n{tender_digest}\n\n"
            f"【我方响应文件全篇章节与页码概览】:\n{resp_outline[:8000]}"
        )

        plan_json, _, _ = await LLM_GATEWAY.chat_json(
            project_id=project_id,
            role="master",
            system_prompt=MASTER_PLANNER_SYSTEM_PROMPT,
            user_prompt=planner_user_prompt,
            temperature=0.1,
            max_tokens=16384,
        )

        final_lot = str(plan_json.get("target_lot") or detected_lot or "").strip().upper()
        raw_items = plan_json.get("items") or []
        valid_cats = set(CATEGORY_LABELS.keys())

        checklist: list[ChecklistItem] = []
        for idx, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict) or not raw.get("title"):
                continue
            cat = str(raw.get("category", "procurement_req")).strip()
            if cat not in valid_cats:
                cat = "procurement_req"
            risk = str(raw.get("risk_level", "score_loss")).strip()
            if risk not in ("fatal", "score_loss", "minor"):
                risk = "score_loss"
            kws = [str(k).strip() for k in (raw.get("search_keywords") or []) if str(k).strip()]
            checklist.append(
                ChecklistItem(
                    item_id=f"CHK-{idx:03d}",
                    order_index=idx - 1,
                    category=cat,  # type: ignore[arg-type]
                    title=str(raw.get("title", "")).strip()[:60],
                    requirement_text=str(raw.get("requirement_text", "")).strip(),
                    tender_source=str(raw.get("tender_source", "")).strip()[:60],
                    risk_level=risk,  # type: ignore[arg-type]
                    requires_vision=bool(raw.get("requires_vision", False)),
                    search_keywords=kws[:8],
                    enabled=True,
                )
            )

        # Always ensure a dedicated Global Redline & Consistency item exists
        if not any("全局形式红线" in it.title or "防串标" in it.title for it in checklist):
            next_idx = len(checklist) + 1
            checklist.append(
                ChecklistItem(
                    item_id=f"CHK-{next_idx:03d}",
                    order_index=next_idx - 1,
                    category="format_redline",
                    title="封面完整性、无待补充留白与防串标一致性核查",
                    requirement_text="封面项目名称、项目编号、分标号、联系人及电话填写完整；全篇无“（待补充）/XXXX/空章节”等未完稿标记；函件抬头与页眉页脚无其他采购人名称或非本标段名称混入；各法定文书落款签章位齐备。",
                    tender_source="第一章及第四章响应文件编制规范",
                    risk_level="fatal",
                    requires_vision=False,
                    search_keywords=["封面", "磋商书", "待补充", "授权书"],
                    enabled=True,
                )
            )

        save_checklist(project_id, checklist)
        est_tokens, est_cost, est_sec = await asyncio.to_thread(
            _estimate_plan_metrics, checklist, response_ast
        )
        proj_title = tender_ast.metadata.get("project_name") or proj.name
        if final_lot and f"{final_lot}标" not in proj_title:
            proj_title = f"{proj_title}（{final_lot}标段）"

        update_project_fields(
            project_id,
            name=proj_title[:60],
            target_lot=final_lot,
            stage="awaiting_confirm",
        )
        await EVENT_BUS.sync_and_broadcast_telemetry(
            project_id,
            stage="awaiting_confirm",
            stage_label="待确认",
            completed_items=0,
            total_items=len(checklist),
            estimated_plan_tokens=est_tokens,
            estimated_plan_cost=est_cost,
            estimated_plan_seconds=est_sec,
        )
        await EVENT_BUS.emit(project_id, "checklist_replaced", {"items": [it.model_dump() for it in checklist]})

        vision_cnt = sum(1 for it in checklist if it.requires_vision)
        fatal_cnt = sum(1 for it in checklist if it.risk_level == "fatal")
        intro = str(plan_json.get("plan_intro") or "").strip()
        if not intro:
            intro = f"已锁定 **{final_lot + '标段' if final_lot else '全部要求'}**，共提取 **{len(checklist)} 项**核查条款。"

        msg_md = (
            f"{intro}\n\n"
            f"- **清单**：`{len(checklist)}` 项（红线 `{fatal_cnt}` · 验图 `{vision_cnt}`）\n"
            f"- **形式预警**：`{len(response_ast.deterministic_findings)}` 处\n"
            f"- **预估**：`~{max(1, round(est_tokens / 1000))}k` Tokens · `~¥{est_cost:.2f}` · `~{est_sec}s`"
        )
        msg = append_message(
            project_id,
            role="assistant",
            content=msg_md,
            msg_type="plan_card",
            meta={
                "target_lot": final_lot,
                "total_items": len(checklist),
                "fatal_items": fatal_cnt,
                "vision_items": vision_cnt,
                "estimated_tokens": est_tokens,
                "estimated_cost": est_cost,
                "estimated_seconds": est_sec,
            },
        )
        await EVENT_BUS.emit(project_id, "chat_message", msg.model_dump())
        return msg
    except asyncio.CancelledError:
        await EVENT_BUS.sync_and_broadcast_telemetry(
            project_id,
            stage="idle",
            stage_label="已停止",
        )
        c_msg = append_message(project_id, "assistant", "已停止生成检查计划。", msg_type="text")
        await EVENT_BUS.emit(project_id, "chat_message", c_msg.model_dump())
        raise
    except Exception:
        await EVENT_BUS.sync_and_broadcast_telemetry(
            project_id,
            stage="error",
            stage_label="规划异常",
        )
        raise
    finally:
        heartbeat_task.cancel()
        await asyncio.gather(heartbeat_task, return_exceptions=True)
        if current_task and _RUNNING_TASKS.get(project_id) is current_task:
            _RUNNING_TASKS.pop(project_id, None)


async def handle_user_chat(project_id: str, user_text: str) -> ChatMessage:
    """Process user's conversational input with Master Agent."""
    proj = get_project(project_id)
    if not proj:
        raise LookupError("项目不存在")

    clean_input = user_text.strip()
    user_msg = append_message(project_id, role="user", content=clean_input, msg_type="text")
    await EVENT_BUS.emit(project_id, "chat_message", user_msg.model_dump())

    # Fast deterministic shortcuts for unambiguous execution commands
    if clean_input in ("开始", "开始检查", "开始核查", "确认", "确认开始", "确认执行", "立即检查"):
        if not proj.checklist:
            if proj.tender_doc and proj.response_doc:
                return await generate_inspection_plan(project_id)
            reply = append_message(project_id, "assistant", "请先导入招标与响应文件。")
            await EVENT_BUS.emit(project_id, "chat_message", reply.model_dump())
            return reply
        started = launch_background_inspection(project_id, recheck_only=False)
        txt = (
            f"已开始并发核查（`{sum(1 for i in proj.checklist if i.enabled)}` 项）。"
            if started
            else "核查正在进行中。"
        )
        reply = append_message(project_id, "assistant", txt)
        await EVENT_BUS.emit(project_id, "chat_message", reply.model_dump())
        return reply

    if clean_input in ("生成清单", "生成检查计划", "重新规划", "重新生成计划"):
        return await generate_inspection_plan(project_id)

    if clean_input in ("复检", "复检问题项", "仅复检问题项", "复查问题项", "重新检查未通过项"):
        started = launch_background_inspection(project_id, recheck_only=True)
        txt = "已开始复检问题项。" if started else "核查正在进行中。"
        reply = append_message(project_id, "assistant", txt)
        await EVENT_BUS.emit(project_id, "chat_message", reply.model_dump())
        return reply

    if not LLM_GATEWAY.has_configured_key("master"):
        reply = append_message(
            project_id,
            "assistant",
            "请先配置 API Key（`⌘,`）。",
        )
        await EVENT_BUS.emit(project_id, "chat_message", reply.model_dump())
        return reply

    # Build rich context for Master Agent conversation
    chk_summary = "\n".join(
        f"- {it.item_id} [{'启用' if it.enabled else '跳过'} | 状态:{it.compliance_status} | 风险:{it.risk_level}] {it.title}: {it.conclusion or it.requirement_text[:80]}"
        for it in proj.checklist[:50]
    )
    rep_summary = ""
    if proj.report:
        rep_summary = (
            f"\n【最新检查报告结论】: {proj.report.verdict_label} (就绪度 {proj.report.readiness_score}/100)\n"
            f"已响应 {proj.report.passed_count} / 待补充 {proj.report.partial_count} / 未响应 {proj.report.missing_count}\n"
            f"摘要：{proj.report.executive_summary}\n"
        )
    recent_history = "\n".join(
        f"{'用户' if m.role == 'user' else 'Master'}: {m.content[:300]}"
        for m in proj.messages[-6:]
    )

    context_prompt = (
        f"【项目状态】: stage={proj.stage}, 目标标段={proj.target_lot or '未指定'}\n"
        f"【已挂载招标文件】: {proj.tender_doc.filename if proj.tender_doc else '未挂载'}\n"
        f"【已挂载响应文件】: {proj.response_doc.filename if proj.response_doc else '未挂载'}\n"
        f"{rep_summary}\n"
        f"【当前检查清单 ({len(proj.checklist)} 项)】:\n{chk_summary or '尚未生成'}\n\n"
        f"【最近对话记录】:\n{recent_history}\n\n"
        f"【用户最新指令】:\n{clean_input}"
    )

    res_json, _, _ = await LLM_GATEWAY.chat_json(
        project_id=project_id,
        role="master",
        system_prompt=MASTER_CHAT_SYSTEM_PROMPT,
        user_prompt=context_prompt,
        temperature=0.2,
        max_tokens=4096,
    )

    action = str(res_json.get("action", "reply")).strip().lower()
    lot_override = str(res_json.get("target_lot_override") or "").strip().upper()
    disable_kws = [str(k).strip() for k in (res_json.get("disable_keywords") or []) if str(k).strip()]
    only_fatal = bool(res_json.get("enable_only_fatal", False))
    reply_md = str(res_json.get("reply_markdown") or "收到。").strip()

    # If user requested switching lot, regenerate plan for that lot
    if lot_override and proj.tender_doc and proj.response_doc and lot_override != proj.target_lot:
        return await generate_inspection_plan(project_id, target_lot_override=lot_override)

    # Apply checklist modifications if any
    plan_modified = False
    if proj.checklist and (disable_kws or only_fatal):
        for it in proj.checklist:
            if only_fatal:
                it.enabled = it.risk_level == "fatal"
                plan_modified = True
            for kw in disable_kws:
                if kw.lower() in it.title.lower() or kw.lower() in it.requirement_text.lower():
                    it.enabled = False
                    plan_modified = True
        if plan_modified:
            save_checklist(project_id, proj.checklist)
            resp_ast = await asyncio.to_thread(_load_response_ast_if_cached, proj)
            est_tok, est_cost, est_sec = await asyncio.to_thread(
                _estimate_plan_metrics, proj.checklist, resp_ast
            )
            await EVENT_BUS.sync_and_broadcast_telemetry(
                project_id,
                total_items=sum(1 for x in proj.checklist if x.enabled),
                estimated_plan_tokens=est_tok,
                estimated_plan_cost=est_cost,
                estimated_plan_seconds=est_sec,
            )
            await EVENT_BUS.emit(
                project_id, "checklist_replaced", {"items": [x.model_dump() for x in proj.checklist]}
            )

    if action == "start_run" and proj.checklist:
        launch_background_inspection(project_id, recheck_only=False)
    elif action == "recheck_issues" and proj.checklist:
        launch_background_inspection(project_id, recheck_only=True)

    reply = append_message(project_id, "assistant", reply_md, msg_type="text")
    await EVENT_BUS.emit(project_id, "chat_message", reply.model_dump())
    return reply
