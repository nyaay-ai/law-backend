from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class ReferenceSource(
    str, Enum
):  # this to track where the reference came from, useful for monitoring and debugging
    CHROMA_CACHE = "cache"
    INDIAN_KANOON = "indian_kanoon"


class LegalReference(BaseModel):
    doc_id: int
    title: str
    text: str  # the relevant passage
    court: Optional[str] = None
    date: Optional[str] = None
    citation: Optional[str] = None
    score: float  # similarity or rerank score
    source: ReferenceSource


class LegalContext(BaseModel):
    references: list[LegalReference]
    cache_hit: bool  # useful for monitoring IK API usage
    draft_context_id: str  # ties back to DraftContext for tracing
    query_used: str


class LegalSearch(BaseModel):
    doc_id: int
    title: str
    fragment: str
    doc_source: str
    citations: list[dict]


class LegalSearchResponse(BaseModel):
    docs: List[LegalSearch]


class DocumentContent(BaseModel):
    doc_id: int
    title: str
    doc: str
    published_date: Optional[str] = None
    num_cites: Optional[int] = None
    doc_source: str


class DraftContext(BaseModel):
    draft_type: str
    intent: str
    urgency: str
    court_type: str
    parties: dict
    facts: List[str]
    legal_issue: str
    dates: List[str]
    jurisdiction: str
    relief: str
    summary: str
    language: str
    missing_fields: List[str]
    confidence: dict
