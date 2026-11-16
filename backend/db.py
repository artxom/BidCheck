"""SQLite repository (WAL mode) for projects, checklist checkpoints, chat messages, token ledger, and settings."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.config import (
    AST_CACHE_DIR,
    DB_PATH,
    MEDIA_CACHE_DIR,
    PROVIDER_PRESETS,
    REPORTS_DIR,
    ROLE_DEFINITIONS,
    UPLOADS_DIR,
    ensure_data_dirs,
)
from backend.schemas import (
    ActiveModelStat,
    AppSettings,
    ChatMessage,
    ChecklistItem,
    DocumentSummary,
    InspectionReport,
    ProjectDetail,
    ProviderConfig,
    RoleRouteConfig,
    TelemetrySnapshot,
)

_DB_LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def get_conn() -> sqlite3.Connection:
    ensure_data_dirs()
    conn = sqlite3.connect(str(DB_PATH), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db() -> None:
    with _DB_LOCK:
        conn = get_conn()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS app_kv (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'idle',
                target_lot TEXT NOT NULL DEFAULT '',
                tender_doc_json TEXT,
                response_doc_json TEXT,
                report_json TEXT,
                telemetry_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS checklist_items (
                project_id TEXT NOT NULL,
                item_id TEXT NOT NULL,
                order_index INTEGER NOT NULL DEFAULT 0,
                data_json TEXT NOT NULL,
                PRIMARY KEY (project_id, item_id),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS messages (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT UNIQUE NOT NULL,
                project_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                msg_type TEXT NOT NULL DEFAULT 'text',
                meta_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS token_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT NOT NULL,
                agent_role TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                model TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                cost REAL NOT NULL DEFAULT 0.0,
                duration_ms INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
        conn.close()


def _build_default_settings() -> AppSettings:
    env_keys = {
        "dashscope": os.environ.get("DASHSCOPE_API_KEY", ""),
        "deepseek": os.environ.get("DEEPSEEK_API_KEY", ""),
        "volcengine": os.environ.get("ARK_API_KEY", ""),
        "siliconflow": os.environ.get("SILICONFLOW_API_KEY", ""),
        "openai": os.environ.get("OPENAI_API_KEY", ""),
        "gemini": os.environ.get("GEMINI_API_KEY", ""),
        "openrouter": os.environ.get("OPENROUTER_API_KEY", ""),
    }

    providers: list[ProviderConfig] = []
    active_default_pid = "dashscope"
    for preset in PROVIDER_PRESETS:
        pid = preset["id"]
        key_val = env_keys.get(pid, "")
        if key_val and active_default_pid == "dashscope" and pid != "dashscope":
            active_default_pid = pid
        providers.append(
            ProviderConfig(
                id=pid,
                name=preset["name"],
                base_url=preset["base_url"],
                api_key=key_val,
                currency=preset.get("currency", "CNY"),
                enabled=True,
            )
        )

    routes: dict[str, RoleRouteConfig] = {
        "master": RoleRouteConfig(
            role="master",
            provider_id=active_default_pid,
            model="qwen-max" if active_default_pid == "dashscope" else "deepseek-chat",
            concurrency=2,
            input_price_per_m=2.4,
            output_price_per_m=9.6,
            enabled=True,
        ),
        "text_worker": RoleRouteConfig(
            role="text_worker",
            provider_id=active_default_pid,
            model="qwen-plus" if active_default_pid == "dashscope" else "deepseek-chat",
            concurrency=6,
            input_price_per_m=0.8,
            output_price_per_m=2.0,
            enabled=True,
        ),
        "vision_worker": RoleRouteConfig(
            role="vision_worker",
            provider_id="dashscope",
            model="qwen-vl-plus",
            concurrency=3,
            input_price_per_m=1.5,
            output_price_per_m=4.5,
            enabled=True,
        ),
        "report_assembler": RoleRouteConfig(
            role="report_assembler",
            provider_id=active_default_pid,
            model="qwen-max" if active_default_pid == "dashscope" else "deepseek-chat",
            concurrency=2,
            input_price_per_m=2.4,
            output_price_per_m=9.6,
            enabled=True,
        ),
    }
    return AppSettings(providers=providers, routes=routes)


def get_settings() -> AppSettings:
    with _DB_LOCK:
        conn = get_conn()
        row = conn.execute("SELECT value FROM app_kv WHERE key = 'settings'").fetchone()
        if not row:
            defaults = _build_default_settings()
            conn.execute(
                "INSERT INTO app_kv (key, value) VALUES ('settings', ?)",
                (defaults.model_dump_json(),),
            )
            conn.commit()
            conn.close()
            return defaults
        conn.close()
        return AppSettings.model_validate_json(row["value"])


def save_settings(settings: AppSettings) -> AppSettings:
    with _DB_LOCK:
        conn = get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO app_kv (key, value) VALUES ('settings', ?)",
            (settings.model_dump_json(),),
        )
        conn.commit()
        conn.close()
        return settings


def create_project(name: str = "新建投标核查项目") -> ProjectDetail:
    pid = f"proj_{uuid.uuid4().hex[:10]}"
    ts = now_iso()
    telemetry = TelemetrySnapshot(project_id=pid, stage="idle", stage_label="就绪")
    with _DB_LOCK:
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO projects (id, name, created_at, updated_at, stage, target_lot, telemetry_json)
            VALUES (?, ?, ?, ?, 'idle', '', ?)
            """,
            (pid, name, ts, ts, telemetry.model_dump_json()),
        )
        conn.commit()
        conn.close()
    return get_project(pid)  # type: ignore[return-value]


def list_projects() -> list[dict[str, Any]]:
    with _DB_LOCK:
        conn = get_conn()
        rows = conn.execute(
            "SELECT id, name, created_at, updated_at, stage, target_lot, tender_doc_json, response_doc_json, telemetry_json FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        conn.close()

    items: list[dict[str, Any]] = []
    for r in rows:
        tel = json.loads(r["telemetry_json"]) if r["telemetry_json"] else {}
        items.append(
            {
                "id": r["id"],
                "name": r["name"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
                "stage": r["stage"],
                "target_lot": r["target_lot"],
                "has_tender": bool(r["tender_doc_json"]),
                "has_response": bool(r["response_doc_json"]),
                "progress_pct": tel.get("progress_pct", 0.0),
                "total_tokens": tel.get("total_tokens", 0),
            }
        )
    return items


def get_project(project_id: str) -> ProjectDetail | None:
    with _DB_LOCK:
        conn = get_conn()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if not row:
            conn.close()
            return None
        chk_rows = conn.execute(
            "SELECT data_json FROM checklist_items WHERE project_id = ? ORDER BY order_index ASC",
            (project_id,),
        ).fetchall()
        msg_rows = conn.execute(
            "SELECT id, project_id, role, content, msg_type, meta_json, created_at FROM messages WHERE project_id = ? ORDER BY seq ASC",
            (project_id,),
        ).fetchall()
        conn.close()

    tender_doc = DocumentSummary.model_validate_json(row["tender_doc_json"]) if row["tender_doc_json"] else None
    response_doc = DocumentSummary.model_validate_json(row["response_doc_json"]) if row["response_doc_json"] else None
    report = InspectionReport.model_validate_json(row["report_json"]) if row["report_json"] else None
    telemetry = TelemetrySnapshot.model_validate_json(row["telemetry_json"])
    checklist = [ChecklistItem.model_validate_json(cr["data_json"]) for cr in chk_rows]
    messages = [
        ChatMessage(
            id=mr["id"],
            project_id=mr["project_id"],
            role=mr["role"],
            content=mr["content"],
            msg_type=mr["msg_type"],
            meta=json.loads(mr["meta_json"] or "{}"),
            created_at=mr["created_at"],
        )
        for mr in msg_rows
    ]

    return ProjectDetail(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        stage=row["stage"],
        target_lot=row["target_lot"],
        tender_doc=tender_doc,
        response_doc=response_doc,
        telemetry=telemetry,
        checklist=checklist,
        report=report,
        messages=messages,
    )


def update_project_fields(project_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return
    kwargs["updated_at"] = now_iso()
    cols = ", ".join(f"{k} = ?" for k in kwargs.keys())
    vals = list(kwargs.values()) + [project_id]
    with _DB_LOCK:
        conn = get_conn()
        conn.execute(f"UPDATE projects SET {cols} WHERE id = ?", vals)
        conn.commit()
        conn.close()


def delete_project(project_id: str) -> bool:
    with _DB_LOCK:
        conn = get_conn()
        cur = conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()
        conn.close()

    # Clean project-specific uploaded files & caches
    for folder in (UPLOADS_DIR, MEDIA_CACHE_DIR, REPORTS_DIR):
        for p in folder.glob(f"*{project_id}*"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            else:
                p.unlink(missing_ok=True)
    for p in AST_CACHE_DIR.glob(f"{project_id}*"):
        p.unlink(missing_ok=True)
    return cur.rowcount > 0


def save_checklist(project_id: str, items: list[ChecklistItem]) -> None:
    with _DB_LOCK:
        conn = get_conn()
        conn.execute("DELETE FROM checklist_items WHERE project_id = ?", (project_id,))
        conn.executemany(
            "INSERT INTO checklist_items (project_id, item_id, order_index, data_json) VALUES (?, ?, ?, ?)",
            [(project_id, it.item_id, idx, it.model_dump_json()) for idx, it in enumerate(items)],
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now_iso(), project_id))
        conn.commit()
        conn.close()


def upsert_checklist_item(project_id: str, item: ChecklistItem) -> None:
    with _DB_LOCK:
        conn = get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO checklist_items (project_id, item_id, order_index, data_json)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, item.item_id, item.order_index, item.model_dump_json()),
        )
        conn.commit()
        conn.close()


def append_message(
    project_id: str,
    role: str,
    content: str,
    msg_type: str = "text",
    meta: dict[str, Any] | None = None,
) -> ChatMessage:
    mid = f"msg_{uuid.uuid4().hex[:10]}"
    ts = now_iso()
    meta_dict = meta or {}
    with _DB_LOCK:
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO messages (id, project_id, role, content, msg_type, meta_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (mid, project_id, role, content, msg_type, json.dumps(meta_dict, ensure_ascii=False), ts),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (ts, project_id))
        conn.commit()
        conn.close()

    return ChatMessage(
        id=mid,
        project_id=project_id,
        role=role,  # type: ignore[arg-type]
        content=content,
        msg_type=msg_type,  # type: ignore[arg-type]
        meta=meta_dict,
        created_at=ts,
    )


def record_token_usage(
    project_id: str,
    agent_role: str,
    provider_id: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost: float,
    duration_ms: int,
) -> None:
    with _DB_LOCK:
        conn = get_conn()
        conn.execute(
            """
            INSERT INTO token_ledger (project_id, agent_role, provider_id, model, prompt_tokens, completion_tokens, cost, duration_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, agent_role, provider_id, model, prompt_tokens, completion_tokens, cost, duration_ms, now_iso()),
        )
        conn.commit()
        conn.close()


def aggregate_project_tokens(project_id: str, active_calls_map: dict[str, int] | None = None) -> tuple[int, int, float, list[ActiveModelStat]]:
    role_labels = {r["role"]: r["label"] for r in ROLE_DEFINITIONS}
    with _DB_LOCK:
        conn = get_conn()
        rows = conn.execute(
            """
            SELECT agent_role, model,
                   COUNT(*) AS calls,
                   SUM(prompt_tokens) AS p_tok,
                   SUM(completion_tokens) AS c_tok,
                   SUM(cost) AS total_cost
            FROM token_ledger
            WHERE project_id = ?
            GROUP BY agent_role, model
            """,
            (project_id,),
        ).fetchall()
        conn.close()

    p_sum, c_sum, cost_sum = 0, 0, 0.0
    stats: list[ActiveModelStat] = []
    seen_roles: set[str] = set()
    active_map = active_calls_map or {}

    for r in rows:
        role = r["agent_role"]
        seen_roles.add(role)
        pt = int(r["p_tok"] or 0)
        ct = int(r["c_tok"] or 0)
        cs = float(r["total_cost"] or 0.0)
        p_sum += pt
        c_sum += ct
        cost_sum += cs
        stats.append(
            ActiveModelStat(
                role=role,
                role_label=role_labels.get(role, role),
                model=r["model"],
                active_calls=active_map.get(role, 0),
                total_calls=int(r["calls"] or 0),
                prompt_tokens=pt,
                completion_tokens=ct,
                total_tokens=pt + ct,
                cost=round(cs, 4),
            )
        )

    # Also surface currently active calls even before their first token ledger write completes
    if active_map:
        settings = get_settings()
        for role, cnt in active_map.items():
            if cnt > 0 and role not in seen_roles:
                route = settings.routes.get(role)
                stats.append(
                    ActiveModelStat(
                        role=role,
                        role_label=role_labels.get(role, role),
                        model=route.model if route else "",
                        active_calls=cnt,
                    )
                )

    return p_sum, c_sum, round(cost_sum, 4), stats


def get_storage_stats() -> dict[str, Any]:
    total_bytes = 0
    for folder in (UPLOADS_DIR, AST_CACHE_DIR, MEDIA_CACHE_DIR, REPORTS_DIR):
        if folder.exists():
            for p in folder.rglob("*"):
                if p.is_file():
                    total_bytes += p.stat().st_size
    return {"cache_bytes": total_bytes, "cache_mb": round(total_bytes / (1024 * 1024), 2)}


def clear_media_and_report_caches() -> dict[str, Any]:
    freed = 0
    for folder in (MEDIA_CACHE_DIR, REPORTS_DIR):
        if folder.exists():
            for p in folder.rglob("*"):
                if p.is_file():
                    freed += p.stat().st_size
            shutil.rmtree(folder, ignore_errors=True)
            folder.mkdir(parents=True, exist_ok=True)
    return {"freed_mb": round(freed / (1024 * 1024), 2)}
