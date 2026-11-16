"""Automated verification for macOS UI bundle, class-based Dark Mode, restrained copy, API edge cases, global redline matching, report failure safety, and handover docs."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

_TEST_TMP_DIR = tempfile.mkdtemp(prefix="bidguard_ui_test_")
os.environ.setdefault("BIDGUARD_DATA_DIR", _TEST_TMP_DIR)

from backend.agents.report_agent import assemble_final_report  # noqa: E402
from backend.agents.worker_engine import _inspect_single_item  # noqa: E402
from backend.config import BASE_DIR, FRONTEND_DIST_DIR  # noqa: E402
from backend.db import create_project, init_db, save_checklist  # noqa: E402
from backend.main import app  # noqa: E402
from backend.parsers.indexer import SectionRetriever  # noqa: E402
from backend.parsers.models import DeterministicFinding, DocumentAST, SectionNode  # noqa: E402
from backend.schemas import CATEGORY_LABELS, ChecklistItem  # noqa: E402


def test_frontend_bundle_dark_mode_and_restrained_copy() -> None:
    index_html = FRONTEND_DIST_DIR / "index.html"
    assert index_html.exists(), "frontend/dist/index.html must be built"
    html_text = index_html.read_text(encoding="utf-8")
    assert "bidguard-theme" in html_text
    assert "prefers-color-scheme: dark" in html_text
    assert "dark:bg-[#161618]" in html_text

    css_files = list((FRONTEND_DIST_DIR / "assets").glob("*.css"))
    assert css_files, "Compiled CSS bundle must exist"
    css_text = css_files[0].read_text(encoding="utf-8")
    # Verify Tailwind v4 class-based dark mode is active (not stuck on media query only)
    assert ":where(.dark" in css_text
    assert "prefers-color-scheme" not in css_text
    for macos_cls in (
        ".macos-toolbar",
        ".macos-sidebar",
        ".macos-card",
        ".macos-popover",
        ".macos-segmented",
        ".macos-btn-primary",
        ".macos-input",
        ".macos-select",
    ):
        assert macos_cls in css_text, f"Missing tactile macOS class {macos_cls}"

    js_files = list((FRONTEND_DIST_DIR / "assets").glob("*.js"))
    assert js_files, "Compiled JS bundle must exist"
    js_text = js_files[0].read_text(encoding="utf-8")

    # Verify concise macOS labels and safe settings cancel action are present
    for concise in ("置入招标与响应文件", "实况", "报告", "原文", "形式预警", "浅色", "深色", "自动", "取消"):
        assert concise in js_text

    # Verify verbose headache-inducing prompts and browser alert() were removed
    for verbose_removed in (
        "挂载招标文件与响应文件后由 Master 自动制定核查计划",
        "内置固有规则扫描预警",
        "点击任意检查项或挂载响应文件后预览原文与扫描件",
        "检查完成后自动在此生成结构化报告",
        "支持手动输入或选预设",
    ):
        assert verbose_removed not in js_text


def test_handover_docs_and_gitignore_guardrails() -> None:
    gitignore = (BASE_DIR / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("*.docx", "*.pdf", "*.xlsx", "data/", ".env", "frontend/dist/", "*.tsbuildinfo"):
        assert pattern in gitignore

    agents_md = BASE_DIR / "AGENTS.md"
    readme = BASE_DIR / "README.md"
    handover = BASE_DIR / "docs" / "HANDOVER.md"
    assert agents_md.exists() and "docs/HANDOVER.md" in agents_md.read_text(encoding="utf-8")
    assert readme.exists() and len(readme.read_text(encoding="utf-8")) > 500
    assert handover.exists()
    handover_text = handover.read_text(encoding="utf-8")
    for required_section in (
        "系统架构与模块职责矩阵",
        "每次阶段执行后的强制交接规程",
        "GitHub 仓库首次绑定与日常同步指南",
        "里程碑交接台账",
        "v0.2.0",
        "v0.3.0",
        "/api/settings/models",
    ):
        assert required_section in handover_text

    # Verify 4-character concise category labels across backend & exports
    assert all(len(label) == 4 for label in CATEGORY_LABELS.values())


@pytest.mark.asyncio
async def test_api_edge_cases_and_spa_security() -> None:
    init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Default project creation uses concise name & stage_label
        r_proj = await client.post("/api/projects", json={})
        assert r_proj.status_code == 200
        proj = r_proj.json()["project"]
        assert proj["name"] == "新建项目"
        assert proj["telemetry"]["stage_label"] == "就绪"
        pid = proj["id"]

        # 2. Empty/whitespace chat message rejected cleanly (400)
        r_empty = await client.post(f"/api/projects/{pid}/chat", json={"message": "   "})
        assert r_empty.status_code == 400

        # 3. Chat & Plan on non-existent project return clean 404 (not 500 ForeignKey IntegrityError!)
        r_chat_404 = await client.post("/api/projects/proj_nonexistent/chat", json={"message": "你好"})
        assert r_chat_404.status_code == 404
        r_plan_404 = await client.post("/api/projects/proj_nonexistent/plan", json={})
        assert r_plan_404.status_code == 404

        # 4. Starting run before checklist exists rejected cleanly (400)
        r_run_early = await client.post(f"/api/projects/{pid}/run", json={"recheck_only": False})
        assert r_run_early.status_code == 400

        # 5. Non-existent project GET returns 404
        r_404 = await client.get("/api/projects/proj_nonexistent")
        assert r_404.status_code == 404

        # 6. Unknown /api/ route returns JSON 404, not SPA HTML
        r_api_404 = await client.get("/api/unknown-endpoint")
        assert r_api_404.status_code == 404
        assert r_api_404.json()["detail"] == "Not Found"

        # 7. Settings endpoint returns concise 4-role labels
        r_settings = await client.get("/api/settings")
        assert r_settings.status_code == 200
        role_labels = [r["label"] for r in r_settings.json()["roles"]]
        assert "主控规划 (Master)" in role_labels
        assert "视觉验图 (Vision)" in role_labels

        # 8. Root serves SPA HTML
        r_root = await client.get("/")
        assert r_root.status_code == 200
        assert "标书智检" in r_root.text


@pytest.mark.asyncio
async def test_global_redline_injection_and_failed_item_report_guard() -> None:
    init_db()
    proj = create_project("红线与失败保护测试")
    pid = proj.id

    cover_sec = SectionNode(
        section_id="sec_0001",
        level=1,
        title="响应文件封面",
        breadcrumb="响应文件封面",
        page_start=1,
        page_end=1,
        paragraphs=["项目名称：测试采购项目", "联系人："],
    )
    other_sec = SectionNode(
        section_id="sec_0002",
        level=1,
        title="技术方案",
        breadcrumb="技术方案",
        page_start=2,
        page_end=5,
        paragraphs=["系统架构说明"],
    )
    det_finding = DeterministicFinding(
        finding_id="det_1",
        rule_type="cover_blank",
        severity="warning",
        title="封面字段「联系人」留空未填",
        detail="封面联系人未填写",
        section_id="sec_0001",
        breadcrumb="响应文件封面",
        page_hint="P1",
        snippet="联系人：",
    )
    ast = DocumentAST(
        doc_id=f"{pid}_resp",
        filename="resp.docx",
        file_type="docx",
        doc_role="response",
        source_path="/tmp/resp.docx",
        file_size_bytes=1024,
        total_pages=5,
        sections=[cover_sec, other_sec],
        deterministic_findings=[det_finding],
    )

    # 1. Verify mandatory global redline title triggers cover section + global_det_summary injection
    redline_item = ChecklistItem(
        item_id="CHK-001",
        order_index=0,
        category="format_redline",
        title="封面完整性、无待补充留白与防串标一致性核查",
        requirement_text="检查封面与待补充标记",
        risk_level="fatal",
        search_keywords=["不存在的关键词XYZ"],
    )
    failed_fatal_item = ChecklistItem(
        item_id="CHK-002",
        order_index=1,
        category="qualification",
        title="营业执照核验",
        requirement_text="提供营业执照",
        risk_level="fatal",
        run_status="failed",
        compliance_status="unchecked",
        conclusion="检查执行异常：Timeout",
    )
    save_checklist(pid, [redline_item, failed_fatal_item])

    captured_prompts: list[str] = []

    async def fake_chat_json(*, user_prompt: str, **_kwargs):
        captured_prompts.append(user_prompt)
        return (
            {
                "compliance_status": "partial",
                "matched_section_ids": ["sec_0001"],
                "evidence_excerpt": "联系人留空",
                "conclusion": "封面联系人未填",
                "remediation": "补齐联系人",
            },
            "mock-model",
            50,
        )

    retriever = SectionRetriever(ast)
    with patch("backend.agents.worker_engine.LLM_GATEWAY.chat_json", new=AsyncMock(side_effect=fake_chat_json)):
        await _inspect_single_item(
            project_id=pid,
            item=redline_item,
            response_ast=ast,
            retriever=retriever,
            outline_brief="sec_0001 响应文件封面",
            det_by_sec={"sec_0001": [det_finding]},
        )

    assert len(captured_prompts) == 1
    assert "【全篇确定性红线扫描汇总】" in captured_prompts[0]
    assert "sec_0001" in captured_prompts[0]

    # 2. Verify report assembler NEVER marks verdict 'ready' when items failed with compliance_status='unchecked'
    save_checklist(pid, [failed_fatal_item])
    with patch("backend.agents.report_agent.LLM_GATEWAY.has_configured_key", return_value=False):
        rep = await assemble_final_report(pid, ast)
    assert rep is not None
    assert rep.overall_verdict == "high_risk"
    assert rep.fatal_issue_count >= 1


@pytest.mark.asyncio
async def test_dynamic_models_api_pricing_and_plan_estimation() -> None:
    import types
    from backend.agents.master_agent import _estimate_plan_metrics
    from backend.config import USD_TO_CNY_RATE
    from backend.db import get_settings, save_settings
    from backend.llm.gateway import LLM_GATEWAY

    init_db()
    LLM_GATEWAY._models_cache.clear()

    # 1. Mock OpenAI/OpenRouter/Gemini style /models responses
    def make_client_cls(payload: dict, status_code: int = 200):
        class _FakeResp:
            def __init__(self) -> None:
                self.status_code = status_code
                self.text = "error"

            def json(self) -> dict:
                return payload

        class _FakeAsyncClient:
            def __init__(self, **_kwargs: object) -> None:
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args: object) -> None:
                return None

            async def get(self, url: str, headers: dict | None = None):
                assert url.endswith("/models")
                assert headers and headers.get("Authorization", "").startswith("Bearer ")
                return _FakeResp()

        return _FakeAsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing credentials -> 400
        r_bad = await client.post("/api/settings/models", json={"base_url": "", "api_key": ""})
        assert r_bad.status_code == 400

        # OpenRouter + catalog + non-chat filtering
        sample_payload = {
            "data": [
                {"id": "text-embedding-3-small"},
                {"id": "whisper-1"},
                {"id": "qwen-plus"},
                {"id": "custom-private-llm"},
                {
                    "id": "anthropic/claude-sonnet-4",
                    "architecture": {"modality": "text+image->text"},
                    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                },
            ]
        }
        with patch("backend.llm.gateway.httpx.AsyncClient", new=make_client_cls(sample_payload)):
            r_models = await client.post(
                "/api/settings/models",
                json={
                    "base_url": "https://openrouter.ai/api/v1",
                    "api_key": "sk-test-models-1",
                    "force_refresh": True,
                },
            )
            assert r_models.status_code == 200
            models = {m["id"]: m for m in r_models.json()["models"]}
            assert "text-embedding-3-small" not in models
            assert "whisper-1" not in models

            assert models["qwen-plus"]["price_source"] == "catalog"
            assert models["qwen-plus"]["input_price"] == 0.8
            assert models["qwen-plus"]["output_price"] == 2.0

            assert models["custom-private-llm"]["price_source"] == "manual"
            assert models["custom-private-llm"]["input_price"] is None

            claude = models["anthropic/claude-sonnet-4"]
            assert claude["vision"] is True
            assert claude["price_source"] == "api"
            assert claude["input_price"] == round(0.000003 * 1_000_000 * USD_TO_CNY_RATE, 4)
            assert claude["output_price"] == round(0.000015 * 1_000_000 * USD_TO_CNY_RATE, 4)

        # Gemini "models/" prefix stripping
        gemini_payload = {
            "data": [
                {"id": "models/gemini-2.5-flash"},
                {"id": "models/gemini-2.5-pro"},
            ]
        }
        with patch("backend.llm.gateway.httpx.AsyncClient", new=make_client_cls(gemini_payload)):
            r_gem = await client.post(
                "/api/settings/models",
                json={
                    "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
                    "api_key": "gem-test-key",
                    "force_refresh": True,
                },
            )
            assert r_gem.status_code == 200
            gem_ids = [m["id"] for m in r_gem.json()["models"]]
            assert "gemini-2.5-flash" in gem_ids
            assert "gemini-2.5-pro" in gem_ids
            assert all(not mid.startswith("models/") for mid in gem_ids)

    # 2. Verify document-grounded _estimate_plan_metrics responds to chunk size & role pricing
    sec_long = SectionNode(
        section_id="sec_0001",
        level=1,
        title="技术实施详细方案",
        breadcrumb="技术实施详细方案",
        page_start=1,
        page_end=10,
        paragraphs=["测试技术响应内容。" * 200],
        media_ids=["img_0001", "img_0002"],
        char_count=1800,
    )
    ast = DocumentAST(
        doc_id="est_doc",
        filename="resp.docx",
        file_type="docx",
        doc_role="response",
        source_path="/tmp/resp.docx",
        file_size_bytes=2048,
        total_pages=10,
        sections=[sec_long],
    )
    items = [
        ChecklistItem(
            item_id="CHK-001",
            order_index=0,
            category="technical_scoring",
            title="技术实施详细方案",
            requirement_text="提供技术实施方案与系统架构",
            requires_vision=True,
            search_keywords=["技术实施"],
            enabled=True,
        )
    ]

    orig_settings = get_settings()
    try:
        mod_settings = orig_settings.model_copy(deep=True)
        mod_settings.routes["text_worker"].input_price_per_m = 1.0
        mod_settings.routes["text_worker"].output_price_per_m = 4.0
        mod_settings.routes["vision_worker"].enabled = True
        mod_settings.routes["vision_worker"].input_price_per_m = 2.0
        mod_settings.routes["vision_worker"].output_price_per_m = 6.0
        save_settings(mod_settings)

        tok1, cost1, eta1 = _estimate_plan_metrics(items, ast)
        assert tok1 > 1500
        assert cost1 > 0
        assert eta1 >= 8

        # Doubling all worker prices roughly doubles cost while tokens remain unchanged
        mod_settings.routes["text_worker"].input_price_per_m = 2.0
        mod_settings.routes["text_worker"].output_price_per_m = 8.0
        mod_settings.routes["vision_worker"].input_price_per_m = 4.0
        mod_settings.routes["vision_worker"].output_price_per_m = 12.0
        mod_settings.routes["report_assembler"].input_price_per_m *= 2
        mod_settings.routes["report_assembler"].output_price_per_m *= 2
        save_settings(mod_settings)

        tok2, cost2, _ = _estimate_plan_metrics(items, ast)
        assert tok2 == tok1
        assert abs(cost2 - cost1 * 2) <= 0.002

        # 3. Verify cached_tokens and direct usage.cost billing in chat_json
        proj = create_project("计费精度测试")
        mod_settings.providers[0].api_key = "sk-billing-test"
        mod_settings.routes["text_worker"].provider_id = mod_settings.providers[0].id
        mod_settings.routes["text_worker"].input_price_per_m = 2.0
        mod_settings.routes["text_worker"].output_price_per_m = 8.0
        save_settings(mod_settings)

        fake_usage = types.SimpleNamespace(
            prompt_tokens=10_000,
            completion_tokens=1_000,
            prompt_cache_hit_tokens=8_000,
        )
        fake_resp = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{"ok": true}'))],
            usage=fake_usage,
        )
        fake_create = AsyncMock(return_value=fake_resp)
        fake_client = types.SimpleNamespace(
            chat=types.SimpleNamespace(completions=types.SimpleNamespace(create=fake_create))
        )
        with patch("backend.llm.gateway.AsyncOpenAI", return_value=fake_client):
            await LLM_GATEWAY.chat_json(
                project_id=proj.id,
                role="text_worker",
                system_prompt="sys",
                user_prompt="usr",
            )
        from backend.db import aggregate_project_tokens

        pt, ct, total_cost, _ = aggregate_project_tokens(proj.id)
        assert pt == 10_000 and ct == 1_000
        # 2000 uncached @ 2.0/M (=0.004) + 8000 cached @ 0.4/M (=0.0032) + 1000 out @ 8.0/M (=0.008) = 0.0152
        assert abs(total_cost - 0.0152) < 1e-4

        # Verify OpenRouter direct usage.cost USD -> CNY conversion
        proj_or = create_project("网关直返费用测试")
        or_prov = next(p for p in mod_settings.providers if p.id == "openrouter")
        or_prov.api_key = "sk-or-test"
        mod_settings.routes["text_worker"].provider_id = "openrouter"
        save_settings(mod_settings)
        fake_usage_or = types.SimpleNamespace(prompt_tokens=500, completion_tokens=100, cost=0.01)
        fake_resp_or = types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=types.SimpleNamespace(content='{"ok": true}'))],
            usage=fake_usage_or,
        )
        with patch(
            "backend.llm.gateway.AsyncOpenAI",
            return_value=types.SimpleNamespace(
                chat=types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=AsyncMock(return_value=fake_resp_or))
                )
            ),
        ):
            await LLM_GATEWAY.chat_json(
                project_id=proj_or.id,
                role="text_worker",
                system_prompt="sys",
                user_prompt="usr",
            )
        _, _, or_cost, _ = aggregate_project_tokens(proj_or.id)
        assert abs(or_cost - 0.01 * USD_TO_CNY_RATE) < 1e-4
    finally:
        save_settings(orig_settings)
