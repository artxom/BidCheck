"""Master Agent: single conversational entry point for tender planning, user adjustments, execution launch, and Q&A."""

from __future__ import annotations

import asyncio
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
    build_response_outline_summary,
    build_tender_digest,
    parse_and_cache_document,
)
from backend.schemas import CATEGORY_LABELS, ChatMessage, ChecklistItem

_RUNNING_TASKS: dict[str, asyncio.Task[Any]] = {}


def is_project_running(project_id: str) -> bool:
    t = _RUNNING_TASKS.get(project_id)
    return bool(t and not t.done())


def launch_background_inspection(project_id: str, recheck_only: bool = False) -> bool:
    if is_project_running(project_id):
        return False
    task = asyncio.create_task(execute_inspection_workflow(project_id, recheck_only=recheck_only))
    _RUNNING_TASKS[project_id] = task
    return True


def _estimate_tokens_and_eta(items: list[ChecklistItem]) -> tuple[int, int]:
    settings = get_settings()
    enabled = [it for it in items if it.enabled]
    vision_cnt = sum(1 for it in enabled if it.requires_vision)
    # ~3,800 tokens per text item + ~2,400 tokens per vision check + ~6,000 report assembly
    est_tokens = len(enabled) * 3800 + vision_cnt * 2400 + 6000
    text_conc = max(1, settings.routes.get("text_worker").concurrency if "text_worker" in settings.routes else 6)
    vision_conc = max(1, settings.routes.get("vision_worker").concurrency if "vision_worker" in settings.routes else 3)
    # ~4.5s avg per text LLM call divided by concurrency + vision calls + 6s report synthesis
    est_sec = int((len(enabled) * 4.8) / text_conc + (vision_cnt * 5.0) / vision_conc + 7)
    return est_tokens, max(8, est_sec)


async def generate_inspection_plan(
    project_id: str,
    target_lot_override: str | None = None,
) -> ChatMessage:
    """Analyze attached Tender + Response ASTs, extract target lot & full checklist via Master Agent, and await confirm."""
    proj = get_project(project_id)
    if not proj or not proj.tender_doc or not proj.response_doc:
        raise ValueError("请先挂载《官方招标文件》与《我方响应文件》后再生成检查计划。")

    await EVENT_BUS.sync_and_broadcast_telemetry(
        project_id,
        stage="planning",
        stage_label="Master 正在拆解招标要求…",
    )

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
        await EVENT_BUS.sync_and_broadcast_telemetry(project_id, stage="idle", stage_label="待配置模型 API Key")
        det_cnt = len(response_ast.deterministic_findings)
        lot_info = f"**{detected_lot} 标段**" if detected_lot else "未区分标段"
        msg = append_message(
            project_id,
            role="assistant",
            content=(
                f"已完成双文档结构拆解：\n"
                f"- **招标文件**：共 `{tender_ast.total_pages}` 页、`{len(tender_ast.sections)}` 个章节、`{tender_ast.total_tables}` 张表格（含标段：{', '.join(tender_ast.detected_lots) or '单标段'}）\n"
                f"- **响应文件**：共 `{response_ast.total_pages}` 页、`{len(response_ast.sections)}` 个章节、`{response_ast.total_images}` 张图片，自动锁定 **{lot_info}**，内置扫描已预先捕获 **{det_cnt} 处**留空/待补充/落款预警。\n\n"
                f"请先点击右上角 **设置图标** 配置大模型 API Key，随后发送「生成检查计划」即可由我为您编排完整核查清单。"
            ),
            msg_type="text",
        )
        await EVENT_BUS.emit(project_id, "chat_message", msg.model_dump())
        return msg

    tender_digest = await asyncio.to_thread(build_tender_digest, tender_ast, detected_lot or None)
    resp_outline = await asyncio.to_thread(build_response_outline_summary, response_ast)

    planner_user_prompt = (
        f"【识别上下文】\n"
        f"- 招标文件名称：{tender_ast.filename}\n"
        f"- 招标文件包含标段：{', '.join(tender_ast.detected_lots) if tender_ast.detected_lots else '不区分标段'}\n"
        f"- 我方响应文件名称：{response_ast.filename}\n"
        f"- 自动检测/指定的我方所投标段：{detected_lot or '请根据响应文件封面与目录判断'}\n\n"
        f"【官方招标/采购文件核心内容（已过滤非目标标段）】:\n{tender_digest}\n\n"
        f"【我方响应文件章节与页码概览（前 160 节）】:\n" + "\n".join(resp_outline.splitlines()[:160])
    )

    plan_json, _, _ = await LLM_GATEWAY.chat_json(
        project_id=project_id,
        role="master",
        system_prompt=MASTER_PLANNER_SYSTEM_PROMPT,
        user_prompt=planner_user_prompt,
        temperature=0.1,
        max_tokens=6000,
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
    est_tokens, est_sec = _estimate_tokens_and_eta(checklist)
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
        stage_label="待确认检查计划",
        completed_items=0,
        total_items=len(checklist),
        estimated_plan_tokens=est_tokens,
        estimated_plan_seconds=est_sec,
    )
    await EVENT_BUS.emit(project_id, "checklist_replaced", {"items": [it.model_dump() for it in checklist]})

    vision_cnt = sum(1 for it in checklist if it.requires_vision)
    fatal_cnt = sum(1 for it in checklist if it.risk_level == "fatal")
    intro = str(plan_json.get("plan_intro") or "").strip()
    if not intro:
        intro = f"已完成招标文件拆解并锁定 **{final_lot + '标段' if final_lot else '全部要求'}**，共规整出 **{len(checklist)} 项**检查目标。"

    msg_md = (
        f"{intro}\n\n"
        f"- **检查项分布**：共 `{len(checklist)}` 项（其中废标红线 `{fatal_cnt}` 项 · 需多模态验图 `{vision_cnt}` 项）\n"
        f"- **固有扫描预警**：已预先定位 `{len(response_ast.deterministic_findings)}` 处留空/待补充/落款提醒\n"
        f"- **预计消耗**：约 `{est_tokens // 1000}k` Tokens · 预计耗时约 `{est_sec}` 秒\n\n"
        f"您可在右侧查看或勾选调整具体条目，也可直接对我说明调整要求（如“跳过荣誉证书检查”），确认无误后点击下方按钮或回复 **「开始检查」**。"
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
            "estimated_seconds": est_sec,
        },
    )
    await EVENT_BUS.emit(project_id, "chat_message", msg.model_dump())
    return msg


async def handle_user_chat(project_id: str, user_text: str) -> ChatMessage:
    """Process user's conversational input with Master Agent."""
    clean_input = user_text.strip()
    user_msg = append_message(project_id, role="user", content=clean_input, msg_type="text")
    await EVENT_BUS.emit(project_id, "chat_message", user_msg.model_dump())

    proj = get_project(project_id)
    if not proj:
        raise ValueError("项目不存在")

    # Fast deterministic shortcuts for unambiguous execution commands
    if clean_input in ("开始", "开始检查", "确认", "确认开始", "确认执行", "立即检查"):
        if not proj.checklist:
            if proj.tender_doc and proj.response_doc:
                return await generate_inspection_plan(project_id)
            reply = append_message(project_id, "assistant", "请先挂载《招标文件》与《响应文件》。")
            await EVENT_BUS.emit(project_id, "chat_message", reply.model_dump())
            return reply
        started = launch_background_inspection(project_id, recheck_only=False)
        txt = (
            f"已启动全量并发检查（共 `{sum(1 for i in proj.checklist if i.enabled)}` 项），可在顶部状态栏与右侧「实况」面板实时查看各模块核查进度。"
            if started
            else "当前检查任务正在运行中，请查看右侧实时进度。"
        )
        reply = append_message(project_id, "assistant", txt)
        await EVENT_BUS.emit(project_id, "chat_message", reply.model_dump())
        return reply

    if clean_input in ("生成检查计划", "重新规划", "重新生成计划"):
        return await generate_inspection_plan(project_id)

    if clean_input in ("复检", "仅复检问题项", "复查问题项", "重新检查未通过项"):
        started = launch_background_inspection(project_id, recheck_only=True)
        txt = "已启动增量复检，仅针对待补充、未响应及异常条目重新核查。" if started else "当前已有检查任务正在运行中。"
        reply = append_message(project_id, "assistant", txt)
        await EVENT_BUS.emit(project_id, "chat_message", reply.model_dump())
        return reply

    if not LLM_GATEWAY.has_configured_key("master"):
        reply = append_message(
            project_id,
            "assistant",
            "尚未配置 Master Agent 的大模型 API Key，请点击右上角设置图标完成配置后再继续对话。",
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
        max_tokens=2000,
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
            est_tok, est_sec = _estimate_tokens_and_eta(proj.checklist)
            await EVENT_BUS.sync_and_broadcast_telemetry(
                project_id,
                total_items=sum(1 for x in proj.checklist if x.enabled),
                estimated_plan_tokens=est_tok,
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
