"""Unified OpenAI-compatible Async LLM Gateway, 4-Role Router, Concurrency Semaphores, and Live SSE Event Bus."""

from __future__ import annotations

import asyncio
import base64
import json
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from backend.db import (
    aggregate_project_tokens,
    get_project,
    get_settings,
    record_token_usage,
    update_project_fields,
)
from backend.schemas import AppSettings, ProviderConfig, RoleRouteConfig, TelemetrySnapshot

THINK_TAG_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def extract_json_payload(raw_text: str) -> dict[str, Any]:
    """Robustly parse a JSON object from LLM output, stripping <think> blocks and markdown code fences."""
    cleaned = THINK_TAG_RE.sub("", raw_text or "").strip()
    m_fence = CODE_FENCE_RE.search(cleaned)
    if m_fence:
        cleaned = m_fence.group(1).strip()

    # Try direct parse first
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"items": parsed}
    except Exception:
        pass

    # Locate outermost '{' ... '}'
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = cleaned[start : end + 1]
        # Remove trailing commas before } or ]
        candidate_fixed = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            parsed = json.loads(candidate_fixed)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    raise ValueError(f"大模型返回内容未能解析为有效 JSON: {cleaned[:200]}")


class ProjectEventBus:
    """In-memory pub/sub SSE hub per project + rolling ETA & live active-call counter."""

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._active_calls: dict[str, dict[str, int]] = {}
        self._run_start_ts: dict[str, float] = {}
        self._item_durations: dict[str, deque[float]] = {}

    def subscribe(self, project_id: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subscribers.setdefault(project_id, set()).add(q)
        return q

    def unsubscribe(self, project_id: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        subs = self._subscribers.get(project_id)
        if subs and q in subs:
            subs.remove(q)

    async def emit(self, project_id: str, event_type: str, data: dict[str, Any]) -> None:
        subs = list(self._subscribers.get(project_id, ()))
        payload = {"event": event_type, "data": data}
        for q in subs:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                    q.put_nowait(payload)
                except Exception:
                    pass

    def mark_run_started(self, project_id: str) -> None:
        self._run_start_ts[project_id] = time.monotonic()
        self._item_durations[project_id] = deque(maxlen=30)

    def record_item_finished(self, project_id: str, duration_sec: float) -> None:
        self._item_durations.setdefault(project_id, deque(maxlen=30)).append(duration_sec)

    def mark_call_delta(self, project_id: str, role: str, delta: int) -> None:
        role_map = self._active_calls.setdefault(project_id, {})
        role_map[role] = max(0, role_map.get(role, 0) + delta)

    def get_active_calls(self, project_id: str) -> dict[str, int]:
        return dict(self._active_calls.get(project_id, {}))

    async def sync_and_broadcast_telemetry(
        self,
        project_id: str,
        stage: str | None = None,
        stage_label: str | None = None,
        completed_items: int | None = None,
        total_items: int | None = None,
        estimated_plan_tokens: int | None = None,
        estimated_plan_seconds: int | None = None,
    ) -> TelemetrySnapshot:
        proj = get_project(project_id)
        cur = proj.telemetry if proj else TelemetrySnapshot(project_id=project_id)

        if stage is not None:
            cur.stage = stage  # type: ignore[assignment]
        if stage_label is not None:
            cur.stage_label = stage_label
        if completed_items is not None:
            cur.completed_items = completed_items
        if total_items is not None:
            cur.total_items = total_items
        if estimated_plan_tokens is not None:
            cur.estimated_plan_tokens = estimated_plan_tokens
        if estimated_plan_seconds is not None:
            cur.estimated_plan_seconds = estimated_plan_seconds

        if cur.total_items > 0:
            cur.progress_pct = round(min(100.0, (cur.completed_items / cur.total_items) * 100.0), 1)
        elif cur.stage == "completed":
            cur.progress_pct = 100.0

        start_ts = self._run_start_ts.get(project_id)
        if start_ts and cur.stage in ("inspecting", "assembling_report"):
            elapsed = max(0.1, time.monotonic() - start_ts)
            cur.elapsed_seconds = round(elapsed, 1)
            remaining = max(0, cur.total_items - cur.completed_items)
            if cur.completed_items >= 1 and remaining > 0:
                rate = cur.completed_items / elapsed  # items per second (naturally accounts for concurrency!)
                cur.eta_seconds = max(2, int(remaining / max(rate, 0.02)))
            elif remaining > 0 and cur.estimated_plan_seconds > 0:
                cur.eta_seconds = max(3, int(cur.estimated_plan_seconds - elapsed))
            else:
                cur.eta_seconds = 2 if cur.stage == "assembling_report" else 0
        elif cur.stage == "completed":
            cur.eta_seconds = 0

        p_tok, c_tok, total_cost, active_models = aggregate_project_tokens(
            project_id, self.get_active_calls(project_id)
        )
        cur.prompt_tokens = p_tok
        cur.completion_tokens = c_tok
        cur.total_tokens = p_tok + c_tok
        cur.estimated_cost = total_cost
        cur.active_models = active_models

        update_fields: dict[str, Any] = {"telemetry_json": cur.model_dump_json()}
        if stage is not None:
            update_fields["stage"] = stage
        update_project_fields(project_id, **update_fields)
        await self.emit(project_id, "telemetry", cur.model_dump())
        return cur


EVENT_BUS = ProjectEventBus()


class LLMGateway:
    """Unified multi-provider OpenAI-compatible client with 4-role routing, concurrency limiting & retries."""

    def __init__(self) -> None:
        self._semaphores: dict[tuple[str, int], asyncio.Semaphore] = {}

    def _get_semaphore(self, role: str, limit: int) -> asyncio.Semaphore:
        eff_limit = max(1, min(32, limit))
        key = (role, eff_limit)
        if key not in self._semaphores:
            self._semaphores[key] = asyncio.Semaphore(eff_limit)
        return self._semaphores[key]

    def resolve_role(
        self, role: str, settings: AppSettings | None = None
    ) -> tuple[ProviderConfig, RoleRouteConfig]:
        cfg = settings or get_settings()
        route = cfg.routes.get(role)
        if not route or not route.enabled:
            raise RuntimeError(f"模型角色「{role}」尚未启用，请在右上角模型配置中绑定。")
        prov_map = {p.id: p for p in cfg.providers}
        provider = prov_map.get(route.provider_id)
        if not provider:
            raise RuntimeError(f"未找到角色「{role}」关联的模型供应商：{route.provider_id}")
        if not provider.api_key.strip():
            raise RuntimeError(f"供应商「{provider.name}」尚未填写 API Key，请点击右上角设置图标完成配置。")
        return provider, route

    def has_configured_key(self, role: str = "master") -> bool:
        try:
            self.resolve_role(role)
            return True
        except Exception:
            return False

    async def chat_json(
        self,
        project_id: str,
        role: str,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[Path] | None = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> tuple[dict[str, Any], str, int]:
        """Invoke the configured role model and parse JSON output. Returns (parsed_dict, model_name, duration_ms)."""
        provider, route = self.resolve_role(role)
        sem = self._get_semaphore(role, route.concurrency)

        # Build OpenAI messages (multimodal if image_paths provided)
        if image_paths:
            content_parts: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            for img_path in image_paths[:4]:
                if img_path and img_path.exists():
                    b64 = base64.b64encode(img_path.read_bytes()).decode("ascii")
                    content_parts.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                        }
                    )
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_parts},
            ]
        else:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

        async with sem:
            EVENT_BUS.mark_call_delta(project_id, role, +1)
            await EVENT_BUS.sync_and_broadcast_telemetry(project_id)
            t0 = time.perf_counter()
            last_err: Exception | None = None
            try:
                client = AsyncOpenAI(
                    api_key=provider.api_key.strip(),
                    base_url=provider.base_url.strip(),
                    timeout=120.0,
                    max_retries=2,
                )
                for attempt in range(2):
                    try:
                        kwargs: dict[str, Any] = {
                            "model": route.model.strip(),
                            "messages": messages,
                            "max_tokens": max_tokens,
                        }
                        # Reasoning models (e.g. deepseek-reasoner / o1 / o3) reject temperature
                        m_lower = route.model.lower()
                        if not any(tag in m_lower for tag in ("reasoner", "o1", "o3", "qwq")):
                            kwargs["temperature"] = temperature

                        resp = await client.chat.completions.create(**kwargs)
                        duration_ms = int((time.perf_counter() - t0) * 1000)

                        raw_content = resp.choices[0].message.content or ""
                        p_tok = int(getattr(resp.usage, "prompt_tokens", 0) or 0)
                        c_tok = int(getattr(resp.usage, "completion_tokens", 0) or 0)
                        if p_tok == 0 and c_tok == 0:
                            # Fallback estimation if a third-party proxy omits usage object
                            p_tok = max(100, len(system_prompt + user_prompt) // 2 + (len(image_paths or []) * 750))
                            c_tok = max(30, len(raw_content) // 2)

                        cost = (
                            (p_tok / 1_000_000.0) * route.input_price_per_m
                            + (c_tok / 1_000_000.0) * route.output_price_per_m
                        )
                        record_token_usage(
                            project_id=project_id,
                            agent_role=role,
                            provider_id=provider.id,
                            model=route.model,
                            prompt_tokens=p_tok,
                            completion_tokens=c_tok,
                            cost=cost,
                            duration_ms=duration_ms,
                        )
                        parsed = extract_json_payload(raw_content)
                        return parsed, route.model, duration_ms
                    except Exception as exc:
                        last_err = exc
                        if attempt == 0:
                            await asyncio.sleep(1.2)
                raise last_err or RuntimeError("LLM 调用失败")
            finally:
                EVENT_BUS.mark_call_delta(project_id, role, -1)
                await EVENT_BUS.sync_and_broadcast_telemetry(project_id)

    async def test_connection(self, base_url: str, api_key: str, model: str) -> dict[str, Any]:
        """Lightweight live connectivity test for Settings modal."""
        t0 = time.perf_counter()
        client = AsyncOpenAI(api_key=api_key.strip(), base_url=base_url.strip(), timeout=25.0, max_retries=0)
        resp = await client.chat.completions.create(
            model=model.strip(),
            messages=[{"role": "user", "content": "请仅回复 OK"}],
            max_tokens=16,
        )
        ms = int((time.perf_counter() - t0) * 1000)
        reply = (resp.choices[0].message.content or "").strip()
        return {"ok": True, "latency_ms": ms, "reply": reply[:60], "model": resp.model}


LLM_GATEWAY = LLMGateway()
