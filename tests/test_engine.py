"""End-to-end automated test suite verifying OOXML parsing, deterministic scanners, multi-agent workflow, and exports."""

from __future__ import annotations

import os
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Isolate test runtime storage before importing backend modules
_TEST_TMP_DIR = tempfile.mkdtemp(prefix="bidguard_test_")
os.environ["BIDGUARD_DATA_DIR"] = _TEST_TMP_DIR

from backend.config import BASE_DIR  # noqa: E402
from backend.db import init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.parsers.indexer import (  # noqa: E402
    SectionRetriever,
    extract_media_jpeg,
    parse_and_cache_document,
)

TENDER_SAMPLE = BASE_DIR / "广西北部湾银行大模型应用场景项目（20261009）竞争性磋商采购文件-发布.docx"
RESPONSE_SAMPLE = BASE_DIR / "广西北部湾银行大模型应用场景项目（20261009）标号：C -竞争性磋商响应文件-11.10-v3.docx"


@pytest.mark.skipif(not TENDER_SAMPLE.exists() or not RESPONSE_SAMPLE.exists(), reason="Sample docx files not in workspace")
def test_real_docx_parsing_and_deterministic_scanners() -> None:
    tender_ast = parse_and_cache_document(TENDER_SAMPLE, "tender", "ut_tender", force_reparse=True)
    assert tender_ast.total_pages == 100
    assert len(tender_ast.detected_lots) == 4
    assert any("C标段" in lot for lot in tender_ast.detected_lots)

    resp_ast = parse_and_cache_document(
        RESPONSE_SAMPLE, "response", "ut_resp", tender_ast_for_response=tender_ast, force_reparse=True
    )
    assert resp_ast.total_pages == 636
    assert resp_ast.metadata.get("target_lot") == "C"
    assert resp_ast.total_images >= 480

    # Verify TOC PAGEREF page anchoring fixed concatenated numbers (ISO9001 should be P25-P27, NOT P125!)
    retriever = SectionRetriever(resp_ast)
    iso_hits = retriever.search("质量管理体系认证证书ISO9001", ["IS09001", "ISO27001"], top_k=4)
    assert any(h.page_start in (25, 27) for h in iso_hits)

    # Verify deterministic redlines catch known defects in v3.docx
    titles = " | ".join(d.title for d in resp_ast.deterministic_findings)
    assert "联系人" in titles
    assert "磋商报价表（待补充）" in titles
    assert "竞标人直接控股、管理关系信息表（待补充）" in titles

    # Verify lazy image transcoding (.png & .tiff -> compressed JPEG)
    first_mid = next(iter(resp_ast.media_index.keys()))
    jpg = extract_media_jpeg(resp_ast, first_mid, max_side=800)
    assert jpg is not None and jpg.exists() and jpg.stat().st_size > 1000


@pytest.mark.asyncio
@pytest.mark.skipif(not TENDER_SAMPLE.exists() or not RESPONSE_SAMPLE.exists(), reason="Sample docx files not in workspace")
async def test_full_api_and_multi_agent_pipeline_with_exports() -> None:
    init_db()

    async def fake_chat_json(
        project_id: str,
        role: str,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[Path] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> tuple[dict[str, Any], str, int]:
        from backend.db import record_token_usage

        record_token_usage(project_id, role, "dashscope", f"mock-{role}", 1200, 300, 0.002, 120)
        if role == "master" and "items" in system_prompt:
            return (
                {
                    "target_lot": "C",
                    "plan_intro": "已锁定 C 标段（风险报告智能生成助手），提取核心检查项。",
                    "items": [
                        {
                            "category": "qualification",
                            "title": "营业执照副本核验",
                            "requirement_text": "提供有效企业法人营业执照副本复印件",
                            "tender_source": "公告六",
                            "risk_level": "fatal",
                            "requires_vision": True,
                            "search_keywords": ["营业执照", "三证合一"],
                        },
                        {
                            "category": "format_redline",
                            "title": "磋商报价表完整性检查",
                            "requirement_text": "按第四章格式完整填写磋商报价表并盖章，不得留空",
                            "tender_source": "第四章格式二",
                            "risk_level": "fatal",
                            "requires_vision": False,
                            "search_keywords": ["磋商报价表"],
                        },
                    ],
                },
                "mock-master",
                150,
            )
        if role == "text_worker":
            if "报价表" in user_prompt:
                return (
                    {
                        "compliance_status": "partial",
                        "matched_section_ids": ["sec_0002"],
                        "evidence_excerpt": "磋商报价表（待补充），表格单价与总价为空",
                        "conclusion": "P7-P9 虽包含磋商报价表章节，但标题注明（待补充）且报价单元格留空。",
                        "remediation": "封标前务必填入最终报价金额并删除“（待补充）”字样。",
                    },
                    "mock-text-worker",
                    90,
                )
            return (
                {
                    "compliance_status": "passed",
                    "matched_section_ids": ["sec_0014"],
                    "evidence_excerpt": "已附最新企业法人营业执照副本扫描件",
                    "conclusion": "P17-P18 已提供三证合一营业执照副本扫描件。",
                    "remediation": "",
                },
                "mock-text-worker",
                80,
            )
        if role == "vision_worker":
            return (
                {
                    "vision_match": True,
                    "downgrade_to": "keep",
                    "vision_note": "图面确系上海安硕信息技术股份有限公司营业执照副本，印章清晰。",
                },
                "mock-vision-worker",
                110,
            )
        if role == "report_assembler":
            return (
                {
                    "overall_verdict": "high_risk",
                    "verdict_label": "存在废标红线待补充项，暂不可封标",
                    "readiness_score": 68,
                    "executive_summary": "主体资质与技术方案响应齐备，但磋商报价表与控股股东表仍处于待补充状态。",
                    "key_risks": ["磋商报价表留空待补充"],
                    "priority_actions": ["补齐报价表与封面联系人电话"],
                },
                "mock-report-assembler",
                140,
            )
        return ({"action": "reply", "reply_markdown": "收到指令。"}, "mock-master", 60)

    with (
        patch("backend.llm.gateway.LLM_GATEWAY.has_configured_key", return_value=True),
        patch("backend.llm.gateway.LLM_GATEWAY.chat_json", new=AsyncMock(side_effect=fake_chat_json)),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Create project
            r_create = await client.post("/api/projects", json={"name": "北部湾测试"})
            assert r_create.status_code == 200
            proj_id = r_create.json()["project"]["id"]

            # 2. Mount both real workspace sample docx files
            r_m1 = await client.post(
                f"/api/projects/{proj_id}/documents/mount-local",
                json={"doc_role": "tender", "filename": TENDER_SAMPLE.name},
            )
            assert r_m1.status_code == 200

            r_m2 = await client.post(
                f"/api/projects/{proj_id}/documents/mount-local",
                json={"doc_role": "response", "filename": RESPONSE_SAMPLE.name},
            )
            assert r_m2.status_code == 200

            # Trigger explicit plan synchronously to verify checklist extraction
            r_plan = await client.post(f"/api/projects/{proj_id}/plan", json={})
            assert r_plan.status_code == 200
            proj_after_plan = r_plan.json()["project"]
            assert proj_after_plan["target_lot"] == "C"
            assert len(proj_after_plan["checklist"]) >= 3  # 2 mocked + 1 auto global redline

            # Execute workflow directly to completion
            from backend.agents.worker_engine import execute_inspection_workflow

            await execute_inspection_workflow(proj_id, recheck_only=False)

            r_done = await client.get(f"/api/projects/{proj_id}")
            done_proj = r_done.json()["project"]
            assert done_proj["stage"] == "completed"
            assert done_proj["report"]["overall_verdict"] == "high_risk"
            assert done_proj["telemetry"]["total_tokens"] > 0

            # Verify Word (.docx) & Excel (.xlsx) exports
            r_docx = await client.get(f"/api/projects/{proj_id}/export/docx")
            assert r_docx.status_code == 200
            assert len(r_docx.content) > 5000

            r_xlsx = await client.get(f"/api/projects/{proj_id}/export/xlsx")
            assert r_xlsx.status_code == 200
            assert len(r_xlsx.content) > 3000
            # Both .docx and .xlsx are valid ZIP archives
            import io

            with zipfile.ZipFile(io.BytesIO(r_docx.content)) as z1:
                assert "word/document.xml" in z1.namelist()
            with zipfile.ZipFile(io.BytesIO(r_xlsx.content)) as z2:
                assert "xl/workbook.xml" in z2.namelist()

            # Verify standalone interactive HTML report export
            r_html = await client.get(f"/api/projects/{proj_id}/export/html")
            assert r_html.status_code == 200
            assert "text/html" in r_html.headers.get("content-type", "")
            html_body = r_html.text
            assert "bidguard-report-snapshot" in html_body
            assert "data:image/webp;base64," in html_body
            assert len(html_body) > 100_000
