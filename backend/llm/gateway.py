"""Unified OpenAI-compatible Async LLM Gateway, 4-Role Router, Concurrency Semaphores, and Live SSE Event Bus."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import re
import time
from collections import deque
from pathlib import Path
from typing import Any

import httpx
from openai import AsyncOpenAI

from backend.config import (
    NON_CHAT_MODEL_RE,
    USD_TO_CNY_RATE,
    infer_vision_capability,
    lookup_model_pricing,
)
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
        estimated_plan_cost: float | None = None,
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
        if estimated_plan_cost is not None:
            cur.estimated_plan_cost = estimated_plan_cost
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

    _MODELS_CACHE_TTL = 300.0

    def __init__(self) -> None:
        self._semaphores: dict[tuple[str, int], asyncio.Semaphore] = {}
        self._models_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}

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
            raise RuntimeError(f"角色「{role}」未启用（⌘,）")
        prov_map = {p.id: p for p in cfg.providers}
        provider = prov_map.get(route.provider_id)
        if not provider:
            raise RuntimeError(f"未找到供应商：{route.provider_id}")
        if not provider.api_key.strip():
            raise RuntimeError(f"请先配置「{provider.name}」API Key（⌘,）")
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
                        usage = getattr(resp, "usage", None)
                        p_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
                        c_tok = int(getattr(usage, "completion_tokens", 0) or 0)
                        if p_tok == 0 and c_tok == 0:
                            # Fallback estimation if a third-party proxy omits usage object
                            p_tok = max(100, len(system_prompt + user_prompt) // 2 + (len(image_paths or []) * 750))
                            c_tok = max(30, len(raw_content) // 2)

                        cached_tok = 0
                        if usage is not None:
                            raw_hit = getattr(usage, "prompt_cache_hit_tokens", None)
                            if raw_hit is None:
                                details = getattr(usage, "prompt_tokens_details", None)
                                if isinstance(details, dict):
                                    raw_hit = details.get("cached_tokens")
                                elif details is not None:
                                    raw_hit = getattr(details, "cached_tokens", None)
                            if raw_hit is not None:
                                try:
                                    cached_tok = max(0, min(p_tok, int(raw_hit)))
                                except (TypeError, ValueError):
                                    cached_tok = 0

                        direct_cost = None
                        if usage is not None:
                            direct_cost = getattr(usage, "cost", None)
                            if direct_cost is None:
                                extra = getattr(usage, "model_extra", None)
                                if isinstance(extra, dict):
                                    direct_cost = extra.get("cost")

                        cost: float | None = None
                        if direct_cost is not None:
                            try:
                                parsed_cost = float(direct_cost)
                                if parsed_cost >= 0:
                                    if provider.id == "openrouter" or provider.currency.upper() == "USD":
                                        cost = parsed_cost * USD_TO_CNY_RATE
                                    else:
                                        cost = parsed_cost
                            except (TypeError, ValueError):
                                cost = None

                        if cost is None:
                            uncached_tok = max(0, p_tok - cached_tok)
                            cost = (
                                (uncached_tok * route.input_price_per_m)
                                + (cached_tok * route.input_price_per_m * 0.2)
                                + (c_tok * route.output_price_per_m)
                            ) / 1_000_000.0
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

    async def list_models(
        self, base_url: str, api_key: str, force_refresh: bool = False
    ) -> list[dict[str, Any]]:
        """Fetch live model inventory from provider's OpenAI-compatible /models endpoint."""
        clean_base = base_url.strip().rstrip("/")
        clean_key = api_key.strip()
        if not clean_base or not clean_key:
            raise ValueError("请先配置 Base URL 与 API Key")

        key_hash = hashlib.sha256(clean_key.encode("utf-8")).hexdigest()[:16]
        cache_key = (clean_base, key_hash)
        now_ts = time.monotonic()
        if not force_refresh and cache_key in self._models_cache:
            cached_ts, cached_list = self._models_cache[cache_key]
            if now_ts - cached_ts < self._MODELS_CACHE_TTL:
                return cached_list

        url = f"{clean_base}/models"
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {clean_key}",
                    "Accept": "application/json",
                },
            )

        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:160]}")

        try:
            payload = resp.json()
        except Exception as exc:
            raise RuntimeError(f"模型列表接口返回非 JSON 内容：{str(exc)[:100]}") from exc

        if isinstance(payload, dict):
            raw_list = payload.get("data")
            if raw_list is None:
                raw_list = payload.get("models")
        elif isinstance(payload, list):
            raw_list = payload
        else:
            raw_list = None

        if not isinstance(raw_list, list):
            raise RuntimeError("模型列表接口返回结构异常（缺少 data 列表）")

        is_google_endpoint = "generativelanguage.googleapis.com" in clean_base.lower()

        def _parse_entry(item: Any) -> dict[str, Any] | None:
            raw_id = ""
            raw_dict: dict[str, Any] | None = None
            if isinstance(item, dict):
                raw_dict = item
                raw_id = str(item.get("id") or item.get("name") or "").strip()
            elif isinstance(item, str):
                raw_id = item.strip()
            if not raw_id:
                return None

            model_id = raw_id[len("models/") :] if (is_google_endpoint and raw_id.startswith("models/")) else raw_id

            in_price: float | None = None
            out_price: float | None = None
            price_source = "manual"

            if raw_dict and isinstance(raw_dict.get("pricing"), dict):
                pricing = raw_dict["pricing"]
                try:
                    p_in = float(pricing.get("prompt"))
                    p_out = float(pricing.get("completion"))
                    if 0.0 <= p_in < 0.05 and 0.0 <= p_out < 0.05:
                        in_price = round(p_in * 1_000_000 * USD_TO_CNY_RATE, 4)
                        out_price = round(p_out * 1_000_000 * USD_TO_CNY_RATE, 4)
                        price_source = "api"
                except (TypeError, ValueError):
                    pass

            if price_source == "manual":
                ref_price = lookup_model_pricing(model_id)
                if ref_price is not None:
                    in_price, out_price = ref_price
                    price_source = "catalog"

            return {
                "id": model_id,
                "vision": infer_vision_capability(model_id, raw_dict),
                "input_price": in_price,
                "output_price": out_price,
                "price_source": price_source,
            }

        all_parsed: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        for entry in raw_list:
            parsed_entry = _parse_entry(entry)
            if parsed_entry and parsed_entry["id"] not in seen_ids:
                seen_ids.add(parsed_entry["id"])
                all_parsed.append(parsed_entry)

        filtered = [m for m in all_parsed if not NON_CHAT_MODEL_RE.search(m["id"])]
        final_models = filtered if filtered else all_parsed
        final_models.sort(key=lambda m: m["id"].lower())

        self._models_cache[cache_key] = (now_ts, final_models)
        return final_models

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
