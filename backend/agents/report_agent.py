"""Report Assembler Agent: aggregates item findings and deterministic redlines into a structured InspectionReport."""

from __future__ import annotations

from backend.db import append_message, get_project, now_iso, update_project_fields
from backend.llm.gateway import EVENT_BUS, LLM_GATEWAY
from backend.llm.prompts import REPORT_ASSEMBLER_SYSTEM_PROMPT
from backend.parsers.models import DocumentAST
from backend.schemas import (
    CATEGORY_LABELS,
    RISK_LABELS,
    STATUS_LABELS,
    CategoryStat,
    InspectionReport,
)


async def assemble_final_report(project_id: str, response_ast: DocumentAST) -> InspectionReport | None:
    proj = get_project(project_id)
    if not proj:
        return None

    enabled_items = [it for it in proj.checklist if it.enabled]
    total = len(enabled_items)
    passed = sum(1 for it in enabled_items if it.compliance_status == "passed")
    partial = sum(1 for it in enabled_items if it.compliance_status == "partial")
    missing = sum(1 for it in enabled_items if it.compliance_status == "missing")

    fatal_issues = sum(
        1 for it in enabled_items if it.risk_level == "fatal" and it.compliance_status in ("partial", "missing")
    ) + sum(1 for d in response_ast.deterministic_findings if d.severity == "fatal")

    score_issues = sum(
        1 for it in enabled_items if it.risk_level == "score_loss" and it.compliance_status in ("partial", "missing")
    )
    minor_issues = sum(
        1 for it in enabled_items if it.risk_level == "minor" and it.compliance_status in ("partial", "missing")
    ) + sum(1 for d in response_ast.deterministic_findings if d.severity == "warning")

    cat_stats: list[CategoryStat] = []
    for cat_key, cat_label in CATEGORY_LABELS.items():
        c_items = [it for it in enabled_items if it.category == cat_key]
        if not c_items:
            continue
        cat_stats.append(
            CategoryStat(
                category=cat_key,
                label=cat_label,
                total=len(c_items),
                passed=sum(1 for it in c_items if it.compliance_status == "passed"),
                partial=sum(1 for it in c_items if it.compliance_status == "partial"),
                missing=sum(1 for it in c_items if it.compliance_status == "missing"),
            )
        )

    await EVENT_BUS.sync_and_broadcast_telemetry(
        project_id,
        stage="assembling_report",
        stage_label="汇总中",
        completed_items=total,
        total_items=total,
    )

    # Build digest of all items & deterministic redlines for Report Assembler Agent
    item_lines: list[str] = []
    for it in enabled_items:
        loc_str = " / ".join(f"{m.breadcrumb}({m.page_label})" for m in it.matched_sections[:2]) or "未定位"
        item_lines.append(
            f"- [{it.item_id}] ({CATEGORY_LABELS.get(it.category)} | {RISK_LABELS.get(it.risk_level)}) "
            f"{it.title} => 【{STATUS_LABELS.get(it.compliance_status, it.compliance_status)}】 "
            f"| 位置: {loc_str} | 结论: {it.conclusion} | 建议: {it.remediation}"
        )

    det_lines = [
        f"- [{d.severity.upper()}] {d.page_hint} {d.breadcrumb}: {d.title} — {d.detail}"
        for d in response_ast.deterministic_findings[:25]
    ]

    assembler_input = (
        f"项目名称：{proj.name}\n"
        f"目标标段：{proj.target_lot or '全标段'}\n"
        f"统计概览：共检查 {total} 项，已响应 {passed} 项，待补充/存疑 {partial} 项，未响应 {missing} 项；"
        f"其中废标红线风险点 {fatal_issues} 处，评分扣分风险 {score_issues} 处，形式瑕疵 {minor_issues} 处。\n\n"
        f"【逐项检查明细】:\n" + "\n".join(item_lines) + "\n\n"
        f"【内置确定性形式扫描发现】:\n" + ("\n".join(det_lines) if det_lines else "无异常")
    )

    # Fallback defaults in case report_assembler API errors at the very end
    default_verdict = "high_risk" if fatal_issues > 0 else ("needs_fix" if (partial + missing) > 0 else "ready")
    default_label = (
        "存在废标红线缺项，严禁直接封标"
        if default_verdict == "high_risk"
        else ("存在待补充项，整改后可封标" if default_verdict == "needs_fix" else "全部要求已响应，具备封标条件")
    )
    base_score = int(round((passed / max(1, total)) * 100)) - (fatal_issues * 12) - (partial * 3)
    default_score = max(0, min(100, base_score))

    verdict = default_verdict
    verdict_label = default_label
    readiness_score = default_score
    exec_summary = (
        f"本次共针对 {total} 项标书要求完成逐章核查：已响应 {passed} 项，待补充 {partial} 项，未响应 {missing} 项。"
        f"系统同时发现 {len(response_ast.deterministic_findings)} 处形式与留空预警，封标前请重点清理所有废标红线与待补充章节。"
    )
    key_risks: list[str] = [
        f"{it.title}（{STATUS_LABELS.get(it.compliance_status)}）：{it.conclusion}"
        for it in enabled_items
        if it.compliance_status in ("missing", "partial")
    ][:6]
    priority_actions: list[str] = [
        it.remediation for it in enabled_items if it.remediation and it.compliance_status in ("missing", "partial")
    ][:6]

    if LLM_GATEWAY.has_configured_key("report_assembler"):
        try:
            rep_json, _, _ = await LLM_GATEWAY.chat_json(
                project_id=project_id,
                role="report_assembler",
                system_prompt=REPORT_ASSEMBLER_SYSTEM_PROMPT,
                user_prompt=assembler_input,
                temperature=0.1,
                max_tokens=2000,
            )
            v_raw = str(rep_json.get("overall_verdict", default_verdict)).lower().strip()
            if v_raw in ("ready", "needs_fix", "high_risk"):
                # Never allow LLM to say "ready" if fatal_issues > 0
                verdict = "high_risk" if (fatal_issues > 0 and v_raw == "ready") else v_raw
            verdict_label = str(rep_json.get("verdict_label") or default_label).strip()
            if isinstance(rep_json.get("readiness_score"), (int, float)):
                readiness_score = max(0, min(100, int(rep_json["readiness_score"])))
            if rep_json.get("executive_summary"):
                exec_summary = str(rep_json["executive_summary"]).strip()
            if isinstance(rep_json.get("key_risks"), list) and rep_json["key_risks"]:
                key_risks = [str(x).strip() for x in rep_json["key_risks"] if str(x).strip()][:8]
            if isinstance(rep_json.get("priority_actions"), list) and rep_json["priority_actions"]:
                priority_actions = [str(x).strip() for x in rep_json["priority_actions"] if str(x).strip()][:8]
        except Exception:
            pass

    report = InspectionReport(
        generated_at=now_iso(),
        project_name=proj.name,
        target_lot=proj.target_lot,
        overall_verdict=verdict,  # type: ignore[arg-type]
        verdict_label=verdict_label,
        readiness_score=readiness_score,
        executive_summary=exec_summary,
        key_risks=key_risks,
        priority_actions=priority_actions,
        total_items=total,
        passed_count=passed,
        partial_count=partial,
        missing_count=missing,
        fatal_issue_count=fatal_issues,
        score_issue_count=score_issues,
        minor_issue_count=minor_issues,
        category_stats=cat_stats,
        deterministic_findings=response_ast.deterministic_findings,
    )

    update_project_fields(project_id, report_json=report.model_dump_json(), stage="completed")
    await EVENT_BUS.sync_and_broadcast_telemetry(
        project_id,
        stage="completed",
        stage_label="已完成",
        completed_items=total,
        total_items=total,
    )
    await EVENT_BUS.emit(project_id, "report_ready", report.model_dump())

    msg_body = (
        f"**{report.verdict_label}** · 就绪度 `{report.readiness_score}/100`\n\n"
        f"- 通过 `{passed}` · 待补充 `{partial}` · 未响应 `{missing}` · 红线 `{fatal_issues}`\n\n"
        f"{report.executive_summary}"
    )
    chat_msg = append_message(
        project_id,
        role="assistant",
        content=msg_body,
        msg_type="report_ready",
        meta={"verdict": report.overall_verdict, "readiness_score": report.readiness_score},
    )
    await EVENT_BUS.emit(project_id, "chat_message", chat_msg.model_dump())
    return report
