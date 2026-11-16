"""Automated verification for macOS UI bundle, class-based Dark Mode, restrained copy, API edge cases, and handover docs."""

from __future__ import annotations

import os
import tempfile

import pytest
from httpx import ASGITransport, AsyncClient

_TEST_TMP_DIR = tempfile.mkdtemp(prefix="bidguard_ui_test_")
os.environ.setdefault("BIDGUARD_DATA_DIR", _TEST_TMP_DIR)

from backend.config import BASE_DIR, FRONTEND_DIST_DIR  # noqa: E402
from backend.db import init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.schemas import CATEGORY_LABELS  # noqa: E402


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
    ):
        assert macos_cls in css_text, f"Missing tactile macOS class {macos_cls}"

    js_files = list((FRONTEND_DIST_DIR / "assets").glob("*.js"))
    assert js_files, "Compiled JS bundle must exist"
    js_text = js_files[0].read_text(encoding="utf-8")

    # Verify concise macOS labels are present
    for concise in ("置入招标与响应文件", "实况", "报告", "原文", "形式预警", "浅色", "深色", "自动"):
        assert concise in js_text

    # Verify verbose headache-inducing prompts were removed
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
    for pattern in ("*.docx", "*.pdf", "*.xlsx", "data/", ".env", "frontend/dist/"):
        assert pattern in gitignore

    readme = BASE_DIR / "README.md"
    handover = BASE_DIR / "docs" / "HANDOVER.md"
    assert readme.exists() and len(readme.read_text(encoding="utf-8")) > 500
    assert handover.exists()
    handover_text = handover.read_text(encoding="utf-8")
    for required_section in (
        "系统架构与模块职责矩阵",
        "每次阶段执行后的强制交接规程",
        "GitHub 仓库首次绑定与日常同步指南",
        "里程碑交接台账",
        "v0.2.0",
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

        # 3. Starting run before checklist exists rejected cleanly (400)
        r_run_early = await client.post(f"/api/projects/{pid}/run", json={"recheck_only": False})
        assert r_run_early.status_code == 400

        # 4. Non-existent project returns 404
        r_404 = await client.get("/api/projects/proj_nonexistent")
        assert r_404.status_code == 404

        # 5. Unknown /api/ route returns JSON 404, not SPA HTML
        r_api_404 = await client.get("/api/unknown-endpoint")
        assert r_api_404.status_code == 404
        assert r_api_404.json()["detail"] == "Not Found"

        # 6. Settings endpoint returns concise 4-role labels
        r_settings = await client.get("/api/settings")
        assert r_settings.status_code == 200
        role_labels = [r["label"] for r in r_settings.json()["roles"]]
        assert "主控规划 (Master)" in role_labels
        assert "视觉验图 (Vision)" in role_labels

        # 7. Root serves SPA HTML
        r_root = await client.get("/")
        assert r_root.status_code == 200
        assert "标书智检" in r_root.text
