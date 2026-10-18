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
    adversarial: list[AdversarialFlag] = Field(default_factory=list)
    ocr_confidence: dict[int, float] = Field(default_factory=dict)  # page -> 0..1, scanned pages only

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
    signals: dict[str, float] = Field(default_factory=dict)  # confidence inputs (analysis/confidence.py)


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


class Conflict(BaseModel):
    """Two places in the document that seem to disagree (or one self-contradictory span)."""
    title: str
    explanation: str
    quote_a: str
    page_a: int
    chunk_a: str = ""
    quote_b: str = ""
    page_b: int = 0
    chunk_b: str = ""
    source: str = "rules"  # rules | llm


class Unusual(BaseModel):
    """A clause worth asking about: one-sided wording, asymmetric terms or atypical wording."""
    title: str
    basis: str  # one-sided wording | asymmetric notice | atypical wording
    explanation: str
    quote: str
    page: int
    chunk_id: str = ""
    quote_b: str = ""
    page_b: int = 0
    similarity: Optional[float] = None


class AdversarialFlag(BaseModel):
    """Content a reader cannot see but a parser would read (hidden text, invisible chars, look-alike letters)."""
    kind: str  # hidden text | invisible characters | look-alike letters
    page: int
    text: str = ""
    detail: str = ""


class JurisdictionInfo(BaseModel):
    state: str = ""
    basis: str = ""      # governing law | courts | place of signing
    value: str = ""
    quote: str = ""
    page: int = 0
    country_law: str = ""


class JurisdictionNote(BaseModel):
    topic: str
    note: str
    quote: str
    page: int


class ClauseChange(BaseModel):
    """One aligned clause pair in a two-version comparison."""
    status: str  # unchanged | modified | added | removed
    old_id: str = ""
    new_id: str = ""
    old_text: str = ""
    new_text: str = ""
    old_page: int = 0
    new_page: int = 0
    diff_html: str = ""
    summary: str = ""
    material: list[str] = Field(default_factory=list)
    explanation: str = ""   # model text, only if both quotes verified
    quote_old: str = ""
    quote_new: str = ""
    similarity: float = 0.0


class GlossaryEntry(BaseModel):
    term: str
    definition: str
    source: str  # glossary | model
    example: str = ""  # the document sentence where the term appears
    page: int = 0


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
    conflicts: list[Conflict] = Field(default_factory=list)
    unusual: list[Unusual] = Field(default_factory=list)
    jurisdiction: JurisdictionInfo = Field(default_factory=JurisdictionInfo)
    jurisdiction_items: list[JurisdictionNote] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    adversarial: list[AdversarialFlag] = Field(default_factory=list)
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
