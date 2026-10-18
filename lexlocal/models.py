"""Pydantic data models shared across the pipeline."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Kind(str, Enum):
    explicit = "explicit"            # the document states this
    interpretation = "interpretation"  # a reasonable reading of what it states
    concern = "concern"              # something worth asking a lawyer about


class Severity(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"


SEVERITY_ORDER = {Severity.high: 0, Severity.medium: 1, Severity.low: 2, Severity.info: 3}


class Page(BaseModel):
    number: int  # 1-based
    text: str
    start: int   # offset of page start in Document.text
    end: int


class Document(BaseModel):
    name: str
    kind: str  # pdf | txt | docx
    pages: list[Page]
    text: str
    warnings: list[str] = Field(default_factory=list)

    def page_for_offset(self, offset: int) -> int:
        for p in self.pages:
            if p.start <= offset < p.end:
                return p.number
        return self.pages[-1].number if self.pages else 1


class Chunk(BaseModel):
    id: str
    heading: str = ""
    text: str
    start: int
    end: int
    page: int
    categories: list[str] = Field(default_factory=list)


class Finding(BaseModel):
    category: str
    title: str
    plain_explanation: str
    quote: str
    chunk_id: str
    page: int
    kind: Kind = Kind.explicit
    severity: Severity = Severity.low
    confidence: float = 0.5
    verified: bool = False
    needs_lawyer: bool = False
    ambiguity_note: Optional[str] = None
    match_score: float = 0.0
    source: str = "llm"  # llm | rules


class Fact(BaseModel):
    """Rule-extracted fact (amount, date, party...) anchored to a verbatim span."""
    type: str
    value: str
    quote: str
    page: int
    start: int
    end: int


class KeyTerm(BaseModel):
    """One row of the structured key-terms table, anchored to a verbatim quote."""
    field: str
    label: str
    value: str
    quote: str
    page: int
    chunk_id: str = ""


class VagueTerm(BaseModel):
    term: str
    quote: str
    page: int
    chunk_id: str


class InjectionFlag(BaseModel):
    pattern: str
    quote: str
    page: int


class StageTiming(BaseModel):
    stage: str
    seconds: float


class Report(BaseModel):
    doc_name: str
    doc_type: str
    summary: str = ""
    summary_verified_quotes: list[Finding] = Field(default_factory=list)
    facts: list[Fact] = Field(default_factory=list)
    key_terms: list[KeyTerm] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    missing_clauses: list[str] = Field(default_factory=list)
    vague_terms: list[VagueTerm] = Field(default_factory=list)
    jurisdiction_notes: list[str] = Field(default_factory=list)
    injection_flags: list[InjectionFlag] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)  # unverified claims, for eval only
    timings: list[StageTiming] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model: str = ""


class QAAnswer(BaseModel):
    question: str
    qtype: str  # document_fact | legal_verdict | out_of_scope
    answer: str
    citations: list[Finding] = Field(default_factory=list)
    silent: bool = False
    escalation: Optional[str] = None
    general_info: Optional[str] = None
    related: list[Chunk] = Field(default_factory=list)
    seconds: float = 0.0
