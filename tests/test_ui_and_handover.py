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
    for pattern in ("*.docx", "*.pdf", "*.xlsx", "data/", ".env", "frontend/dist/", "*.tsbuildinfo", "release/", "BidGuard-*.zip"):
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
        "v0.4.0",
        "v0.5.0",
        "BidGuard-Windows-x64.zip",
        "/api/settings/models",
        "/cancel",
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


@pytest.mark.asyncio
async def test_zero_token_precheck_and_trimmed_tender_digest() -> None:
    from backend.parsers.indexer import (
        build_response_outline_summary,
        build_tender_digest,
        parse_and_cache_document,
    )

    tender_sample = BASE_DIR / "广西北部湾银行大模型应用场景项目（20261009）竞争性磋商采购文件-发布.docx"
    response_sample = BASE_DIR / "广西北部湾银行大模型应用场景项目（20261009）标号：C -竞争性磋商响应文件-11.10-v3.docx"
    if not tender_sample.exists() or not response_sample.exists():
        pytest.skip("Sample docx files not in workspace")

    init_db()
    tender_ast = parse_and_cache_document(tender_sample, "tender", "ut_v4_tender", force_reparse=True)
    resp_ast = parse_and_cache_document(
        response_sample, "response", "ut_v4_resp", tender_ast_for_response=tender_ast, force_reparse=True
    )

    # 1. Verify Ch5 boilerplate is completely excluded & Ch3/Ch4 non-functional specs are intact
    digest = build_tender_digest(tender_ast, "C")
    assert len(digest) < 48_000
    assert "保密协议" not in digest
    assert "术语及定义" not in digest
    assert "十一、非功能需求满足情况表" in digest
    assert "非功能需求" in digest
    # Verify non-functional section (>6,000 chars) wasn't truncated at 4,500
    nonfunc_sec = next(s for s in tender_ast.sections if s.title == "非功能需求")
    assert nonfunc_sec.char_count > 6000
    assert nonfunc_sec.paragraphs[-1][:30] in digest

    # 2. Verify compact response outline covers entire 636-page document under 5,000 chars
    compact_outline = build_response_outline_summary(resp_ast, compact=True)
    assert len(compact_outline) < 5000
    assert "其他文书、文件" in compact_outline

    # 3. Verify mounting both documents performs 0 LLM calls and emits precheck_card
    with (
        patch("backend.llm.gateway.LLM_GATEWAY.has_configured_key", return_value=True),
        patch("backend.llm.gateway.LLM_GATEWAY.chat_json", new=AsyncMock()) as mock_chat,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r_p = await client.post("/api/projects", json={"name": "零消耗预检测试"})
            pid = r_p.json()["project"]["id"]
            await client.post(
                f"/api/projects/{pid}/documents/mount-local",
                json={"doc_role": "tender", "filename": tender_sample.name},
            )
            r_m2 = await client.post(
                f"/api/projects/{pid}/documents/mount-local",
                json={"doc_role": "response", "filename": response_sample.name},
            )
            assert r_m2.status_code == 200
            proj = r_m2.json()["project"]
            assert mock_chat.call_count == 0
            assert proj["stage"] == "idle"
            assert proj["telemetry"]["stage_label"] == "待生成清单"
            assert proj["target_lot"] == "C"
            pre_msgs = [m for m in proj["messages"] if m["msg_type"] == "precheck_card"]
            assert len(pre_msgs) == 1
            assert pre_msgs[0]["meta"]["target_lot"] == "C"
            assert len(pre_msgs[0]["meta"]["detected_lots"]) == 4
            assert pre_msgs[0]["meta"]["est_plan_input_tokens"] > 1000


@pytest.mark.asyncio
async def test_reasoning_truncation_no_retry_effort_fallback_and_cancel() -> None:
    import asyncio
    import types
    import httpx
    from openai import BadRequestError
    from backend.config import MODEL_PRICING_RULES
    from backend.db import get_settings, save_settings
    from backend.llm.gateway import LLM_GATEWAY, NonRetryableLLMError

    # Ensure user's "4 不需要，我手工上传价目即可" instruction was respected
    assert not any("deepseek-v4" in pat.pattern.lower() for pat, _, _ in MODEL_PRICING_RULES)

    init_db()
    orig_settings = get_settings()
    try:
        mod_settings = orig_settings.model_copy(deep=True)
        mod_settings.providers[0].api_key = "sk-v4-test"
        mod_settings.routes["master"].provider_id = mod_settings.providers[0].id
        mod_settings.routes["master"].model = "deepseek-v4-pro"
        save_settings(mod_settings)
        LLM_GATEWAY._model_caps["deepseek-v4-pro"] = {"supports_effort": True}

        proj = create_project("截断与取消测试")

        # 1. Truncated reasoning response (finish_reason='length', content='') must NOT retry
        trunc_usage = types.SimpleNamespace(
            prompt_tokens=20_000,
            completion_tokens=6_000,
            completion_tokens_details=types.SimpleNamespace(reasoning_tokens=6_000),
        )
        trunc_resp = types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    finish_reason="length",
                    message=types.SimpleNamespace(content=""),
                )
            ],
            usage=trunc_usage,
        )
        mock_create_trunc = AsyncMock(return_value=trunc_resp)
        with patch(
            "backend.llm.gateway.AsyncOpenAI",
            return_value=types.SimpleNamespace(
                chat=types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=mock_create_trunc)
                )
            ),
        ):
            with pytest.raises(NonRetryableLLMError) as exc_info:
                await LLM_GATEWAY.chat_json(
                    project_id=proj.id,
                    role="master",
                    system_prompt="sys",
                    user_prompt="usr",
                    max_tokens=6000,
                )
        assert mock_create_trunc.call_count == 1
        assert "截断" in str(exc_info.value)
        assert "6000" in str(exc_info.value)

        # 2. HTTP 400 rejecting reasoning_effort triggers 0-token downgrade & caches capability
        recorded_kwargs: list[dict] = []

        async def bad_request_then_ok(**kwargs):
            recorded_kwargs.append(dict(kwargs))
            if "reasoning_effort" in kwargs:
                raise BadRequestError(
                    "Unknown field: reasoning_effort",
                    response=httpx.Response(
                        400,
                        request=httpx.Request("POST", "https://api.example.com/v1/chat/completions"),
                    ),
                    body=None,
                )
            return types.SimpleNamespace(
                choices=[
                    types.SimpleNamespace(
                        finish_reason="stop",
                        message=types.SimpleNamespace(content='{"ok": true}'),
                    )
                ],
                usage=types.SimpleNamespace(prompt_tokens=100, completion_tokens=20),
            )

        with patch(
            "backend.llm.gateway.AsyncOpenAI",
            return_value=types.SimpleNamespace(
                chat=types.SimpleNamespace(
                    completions=types.SimpleNamespace(create=AsyncMock(side_effect=bad_request_then_ok))
                )
            ),
        ):
            parsed, _, _ = await LLM_GATEWAY.chat_json(
                project_id=proj.id,
                role="master",
                system_prompt="sys",
                user_prompt="usr",
            )
        assert parsed == {"ok": True}
        assert len(recorded_kwargs) == 2
        assert recorded_kwargs[0].get("reasoning_effort") == "low"
        assert "reasoning_effort" not in recorded_kwargs[1]
        assert LLM_GATEWAY._model_caps["deepseek-v4-pro"].get("rejects_effort") is True

        # 3. Verify /plan failure transitions stage to 'error' (never stuck in 'planning') and /cancel stops running plan
        tender_sample = BASE_DIR / "广西北部湾银行大模型应用场景项目（20261009）竞争性磋商采购文件-发布.docx"
        response_sample = BASE_DIR / "广西北部湾银行大模型应用场景项目（20261009）标号：C -竞争性磋商响应文件-11.10-v3.docx"
        if tender_sample.exists() and response_sample.exists():
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                with patch("backend.llm.gateway.LLM_GATEWAY.has_configured_key", return_value=True):
                    r_p = await client.post("/api/projects", json={"name": "状态机保护测试"})
                    pid = r_p.json()["project"]["id"]
                    await client.post(
                        f"/api/projects/{pid}/documents/mount-local",
                        json={"doc_role": "tender", "filename": tender_sample.name},
                    )
                    await client.post(
                        f"/api/projects/{pid}/documents/mount-local",
                        json={"doc_role": "response", "filename": response_sample.name},
                    )

                    # 3a. Failed /plan leaves stage='error'
                    with patch(
                        "backend.llm.gateway.LLM_GATEWAY.chat_json",
                        new=AsyncMock(side_effect=NonRetryableLLMError("截断测试")),
                    ):
                        r_fail = await client.post(f"/api/projects/{pid}/plan", json={"async_run": False})
                    assert r_fail.status_code == 400
                    r_after_fail = await client.get(f"/api/projects/{pid}")
                    assert r_after_fail.json()["project"]["stage"] == "error"

                    # 3b. Async /plan can be cancelled via /cancel cleanly
                    started_evt = asyncio.Event()

                    async def slow_chat(**_kwargs):
                        started_evt.set()
                        await asyncio.sleep(10)
                        return ({}, "m", 10)

                    with patch(
                        "backend.llm.gateway.LLM_GATEWAY.chat_json",
                        new=AsyncMock(side_effect=slow_chat),
                    ):
                        r_start = await client.post(
                            f"/api/projects/{pid}/plan", json={"async_run": True}
                        )
                        assert r_start.status_code == 200
                        await asyncio.wait_for(started_evt.wait(), timeout=5.0)
                        r_cancel = await client.post(f"/api/projects/{pid}/cancel")
                        assert r_cancel.status_code == 200
                        assert r_cancel.json()["cancelled"] is True
                        assert r_cancel.json()["project"]["stage"] == "idle"
                        assert r_cancel.json()["project"]["telemetry"]["stage_label"] == "已停止"
    finally:
        LLM_GATEWAY._model_caps.pop("deepseek-v4-pro", None)
        save_settings(orig_settings)


def test_windows_packaging_frozen_paths_and_launcher_selftest(tmp_path) -> None:
    import importlib.util
    import json
    import subprocess
    import sys
    import zipfile

    import docx

    from backend.config import resolve_runtime_paths
    from backend.db import get_project, update_project_fields
    from backend.exporters.docx_exporter import build_docx_report
    from backend.exporters.xlsx_exporter import build_xlsx_checklist
    from backend.parsers.indexer import parse_and_cache_document
    from backend.schemas import CategoryStat, InspectionReport

    # 1. Simulated PyInstaller frozen runtime paths
    fake_dir = tmp_path / "portable_bidguard"
    fake_dir.mkdir(parents=True, exist_ok=True)
    fake_internal = fake_dir / "_internal"
    fake_internal.mkdir(parents=True, exist_ok=True)
    resolved = resolve_runtime_paths(
        is_frozen=True,
        meipass=fake_internal,
        executable=fake_dir / "BidGuard.exe",
        env={},
    )
    assert resolved["FRONTEND_DIST_DIR"] == fake_internal.resolve() / "frontend" / "dist"
    assert resolved["DATA_DIR"] == fake_dir.resolve() / "data"
    assert resolved["BASE_DIR"] == fake_dir.resolve()

    # 2. Windows icon generation
    icon_mod_spec = importlib.util.spec_from_file_location(
        "bidguard_generate_icon", BASE_DIR / "packaging" / "generate_icon.py"
    )
    assert icon_mod_spec is not None and icon_mod_spec.loader is not None
    icon_mod = importlib.util.module_from_spec(icon_mod_spec)
    icon_mod_spec.loader.exec_module(icon_mod)
    ico_path = tmp_path / "bidguard.ico"
    icon_mod.generate_bidguard_ico(ico_path)
    assert ico_path.exists() and ico_path.stat().st_size > 1000
    assert ico_path.read_bytes()[:4] == b"\x00\x00\x01\x00"

    # 3. Launcher standalone --self-test subprocess execution
    selftest_json = tmp_path / "selftest.json"
    env = dict(os.environ)
    env["BIDGUARD_DATA_DIR"] = str(tmp_path / "selftest_data")
    proc = subprocess.run(
        [
            sys.executable,
            str(BASE_DIR / "launcher.py"),
            "--self-test",
            "--self-test-out",
            str(selftest_json),
        ],
        cwd=str(BASE_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, f"launcher --self-test failed: {proc.stderr}"
    assert "SELF_TEST_OK" in proc.stdout
    selftest_payload = json.loads(selftest_json.read_text(encoding="utf-8"))
    assert selftest_payload["ok"] is True

    # 4. Synthetic .docx parse + Word/Excel export verification (runs on CI without confidential fixtures)
    init_db()
    synth_docx = tmp_path / "synthetic_response.docx"
    doc = docx.Document()
    doc.add_heading("第一章 资格审查要求", level=1)
    doc.add_paragraph("已附营业执照副本，系统架构完整。")
    tbl = doc.add_table(rows=2, cols=2)
    tbl.cell(0, 0).text = "核查项"
    tbl.cell(0, 1).text = "响应情况"
    tbl.cell(1, 0).text = "营业执照"
    tbl.cell(1, 1).text = "已提供"
    doc.save(synth_docx)

    ast = parse_and_cache_document(synth_docx, "response", "ut_synth_resp", force_reparse=True)
    assert len(ast.sections) >= 1

    proj = create_project("CI合成导出测试")
    item = ChecklistItem(
        item_id="CHK-SYNTH-1",
        order_index=0,
        category="qualification",
        title="营业执照副本核验",
        requirement_text="提供营业执照副本",
        risk_level="fatal",
        run_status="completed",
        compliance_status="passed",
        matched_section_ids=[ast.sections[0].section_id],
        conclusion="已提供营业执照副本。",
    )
    save_checklist(proj.id, [item])
    rep = InspectionReport(
        project_id=proj.id,
        generated_at="2026-11-16T19:30:00",
        overall_verdict="ready",
        verdict_label="核查通过，可封标",
        readiness_score=100,
        total_items=1,
        passed_count=1,
        partial_count=0,
        missing_count=0,
        fatal_issue_count=0,
        deterministic_finding_count=len(ast.deterministic_findings),
        executive_summary="合成测试文档全部响应。",
        category_stats=[CategoryStat(category="qualification", label="资格审查", total=1, passed=1)],
    )
    update_project_fields(proj.id, report_json=rep.model_dump_json())
    loaded_proj = get_project(proj.id)
    assert loaded_proj is not None
    out_docx = build_docx_report(loaded_proj)
    out_xlsx = build_xlsx_checklist(loaded_proj)
    assert out_docx.exists() and out_docx.stat().st_size > 3000
    assert out_xlsx.exists() and out_xlsx.stat().st_size > 2000
    with zipfile.ZipFile(out_docx) as z_doc:
        assert "word/document.xml" in z_doc.namelist()
    with zipfile.ZipFile(out_xlsx) as z_xls:
        assert "xl/workbook.xml" in z_xls.namelist()

    # 5. Verify Windows packaging & GitHub Actions release files
    workflow_file = BASE_DIR / ".github" / "workflows" / "release.yml"
    spec_file = BASE_DIR / "packaging" / "bidguard.spec"
    ps_script = BASE_DIR / "scripts" / "build_windows.ps1"
    assert workflow_file.exists() and spec_file.exists() and ps_script.exists()
    wf_text = workflow_file.read_text(encoding="utf-8")
    for expected in ("windows-latest", "BidGuard-Windows-x64.zip", "softprops/action-gh-release"):
        assert expected in wf_text
    assert "--self-test" in ps_script.read_text(encoding="utf-8")

