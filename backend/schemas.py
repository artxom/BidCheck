"""Core Pydantic schemas for settings, checklist items, telemetry, chat, and inspection reports."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

from backend.parsers.models import DeterministicFinding


CategoryType = Literal[
    "qualification",       # 资格与符合性审查
    "commercial_scoring",  # 商务与资信评分项
    "technical_scoring",   # 技术与服务评分项
    "procurement_req",     # 采购需求响应（功能/非功能/实施维保）
    "format_redline",      # 响应文件格式与形式红线
]

CATEGORY_LABELS: dict[str, str] = {
    "qualification": "资格审查",
    "commercial_scoring": "商务资信",
    "technical_scoring": "技术方案",
    "procurement_req": "采购需求",
    "format_redline": "形式红线",
}

RISK_LABELS: dict[str, str] = {
    "fatal": "废标红线",
    "score_loss": "扣分风险",
    "minor": "形式瑕疵",
}

STATUS_LABELS: dict[str, str] = {
    "unchecked": "待检查",
    "passed": "已响应",
    "partial": "待补充",
    "missing": "未响应",
}


class ProviderConfig(BaseModel):
    id: str
    name: str
    base_url: str
    api_key: str = ""
    currency: str = "CNY"
    enabled: bool = True


class RoleRouteConfig(BaseModel):
    role: Literal["master", "text_worker", "vision_worker", "report_assembler"]
    provider_id: str = "dashscope"
    model: str = "qwen-plus"
    concurrency: int = 4
    input_price_per_m: float = 0.8   # Price per 1M prompt tokens
    output_price_per_m: float = 2.0  # Price per 1M completion tokens
    enabled: bool = True


class AppSettings(BaseModel):
    providers: list[ProviderConfig] = Field(default_factory=list)
    routes: dict[str, RoleRouteConfig] = Field(default_factory=dict)


class MatchedSectionRef(BaseModel):
    section_id: str
    breadcrumb: str
    page_label: str


class ChecklistItem(BaseModel):
    item_id: str
    order_index: int = 0
    category: CategoryType = "procurement_req"
    title: str
    requirement_text: str
    tender_source: str = ""
    risk_level: Literal["fatal", "score_loss", "minor"] = "score_loss"
    requires_vision: bool = False
    search_keywords: list[str] = Field(default_factory=list)
    enabled: bool = True

    # Execution & result fields
    run_status: Literal["pending", "running", "completed", "skipped", "failed"] = "pending"
    compliance_status: Literal["unchecked", "passed", "partial", "missing"] = "unchecked"
    matched_sections: list[MatchedSectionRef] = Field(default_factory=list)
    evidence_excerpt: str = ""
    media_ids: list[str] = Field(default_factory=list)
    vision_verified: bool = False
    vision_note: str = ""
    conclusion: str = ""
    remediation: str = ""
    checked_by_model: str = ""
    duration_ms: int = 0


class ActiveModelStat(BaseModel):
    role: str
    role_label: str
    model: str
    active_calls: int = 0
    total_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


class TelemetrySnapshot(BaseModel):
    project_id: str
    stage: Literal[
        "idle",
        "parsing",
        "planning",
        "awaiting_confirm",
        "inspecting",
        "assembling_report",
        "completed",
        "error",
    ] = "idle"
    stage_label: str = "就绪"
    completed_items: int = 0
    total_items: int = 0
    progress_pct: float = 0.0
    eta_seconds: int | None = None
    elapsed_seconds: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    currency: str = "CNY"
    estimated_plan_tokens: int = 0
    estimated_plan_cost: float = 0.0
    estimated_plan_seconds: int = 0
    active_models: list[ActiveModelStat] = Field(default_factory=list)


class CategoryStat(BaseModel):
    category: str
    label: str
    total: int = 0
    passed: int = 0
    partial: int = 0
    missing: int = 0


class InspectionReport(BaseModel):
    generated_at: str
    project_name: str = ""
    target_lot: str = ""
    overall_verdict: Literal["ready", "needs_fix", "high_risk"] = "needs_fix"
    verdict_label: str = ""
    readiness_score: int = 0
    executive_summary: str = ""
    key_risks: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)
    total_items: int = 0
    passed_count: int = 0
    partial_count: int = 0
    missing_count: int = 0
    fatal_issue_count: int = 0
    score_issue_count: int = 0
    minor_issue_count: int = 0
    category_stats: list[CategoryStat] = Field(default_factory=list)
    deterministic_findings: list[DeterministicFinding] = Field(default_factory=list)


class DocumentSummary(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    doc_role: str
    file_size_bytes: int
    total_pages: int
    total_chars: int
    total_tables: int
    total_images: int
    detected_lots: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    deterministic_count: int = 0


class ChatMessage(BaseModel):
    id: str
    project_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    msg_type: Literal["text", "precheck_card", "plan_card", "report_ready", "error"] = "text"
    meta: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ProjectDetail(BaseModel):
    id: str
    name: str
    created_at: str
    updated_at: str
    stage: str
    target_lot: str = ""
    tender_doc: DocumentSummary | None = None
    response_doc: DocumentSummary | None = None
    telemetry: TelemetrySnapshot
    checklist: list[ChecklistItem] = Field(default_factory=list)
    report: InspectionReport | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
