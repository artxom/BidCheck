"""Structured AST models for parsed Word (.docx) and PDF (.pdf) documents."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

CURRENT_AST_VERSION = 2


class MediaRef(BaseModel):
    media_id: str
    rel_id: str = ""
    source_key: str = ""  # zip entry path (e.g. word/media/image1.png) or pdf page:xref
    ext: str = ".png"
    width_px: int = 0
    height_px: int = 0
    section_id: str = ""
    breadcrumb: str = ""
    page_hint: str = ""
    context_text: str = ""


class EmptyCellAlert(BaseModel):
    row_idx: int
    col_idx: int
    col_header: str = ""
    row_context: str = ""


class TableBlock(BaseModel):
    table_id: str
    section_id: str = ""
    row_count: int = 0
    col_count: int = 0
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    markdown: str = ""
    media_ids: list[str] = Field(default_factory=list)
    empty_cells: list[EmptyCellAlert] = Field(default_factory=list)
    page_hint: str = ""


class SectionNode(BaseModel):
    section_id: str
    order_index: int = 0
    level: int = 1  # 0 = Cover / Frontmatter, 1..6 = H1..H6
    title: str
    breadcrumb: str
    parent_id: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    paragraphs: list[str] = Field(default_factory=list)
    tables: list[TableBlock] = Field(default_factory=list)
    media_ids: list[str] = Field(default_factory=list)
    char_count: int = 0

    @property
    def page_label(self) -> str:
        if self.page_start and self.page_end:
            if self.page_start == self.page_end:
                return f"P{self.page_start}"
            return f"P{self.page_start}-P{self.page_end}"
        if self.page_start:
            return f"P{self.page_start}"
        return "页码未锚定"


class DeterministicFinding(BaseModel):
    finding_id: str
    rule_type: Literal[
        "cover_blank",
        "placeholder_text",
        "empty_table_cell",
        "wrong_entity_or_lot",
        "seal_signature_slot",
        "empty_section",
    ]
    severity: Literal["fatal", "warning", "info"] = "warning"
    title: str
    detail: str
    section_id: str = ""
    breadcrumb: str = ""
    page_hint: str = ""
    snippet: str = ""


class DocumentAST(BaseModel):
    ast_version: int = 1
    doc_id: str
    filename: str
    source_path: str
    file_type: Literal["docx", "pdf"]
    doc_role: Literal["tender", "response"]
    file_size_bytes: int = 0
    total_pages: int = 0
    total_chars: int = 0
    total_tables: int = 0
    total_images: int = 0
    cover_lines: list[str] = Field(default_factory=list)
    headers_footers: list[str] = Field(default_factory=list)
    toc_entries: list[dict[str, Any]] = Field(default_factory=list)
    detected_lots: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    sections: list[SectionNode] = Field(default_factory=list)
    media_index: dict[str, MediaRef] = Field(default_factory=dict)
    deterministic_findings: list[DeterministicFinding] = Field(default_factory=list)
