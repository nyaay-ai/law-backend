from typing import Optional

from pydantic import BaseModel


class CaseInfo(BaseModel):
    case_id: str
    case_name: str
    court_name: str
    filing_date: Optional[str] = None
    last_hearing_date: Optional[str] = None
    next_hearing_date: Optional[str] = None
    advocate_name: Optional[str] = None
    case_number: Optional[str] = None
    case_status: Optional[str] = None
    case_type: Optional[str] = None
    notes: Optional[str] = None


class CaseListResponse(BaseModel):
    cases: list[CaseInfo]
    total_cases: int
    active_cases: int
    closed_cases: int


class DraftInfo(BaseModel):
    case_id: str
    draft_name: str
    court_name: str
    created_at: str
    case_type: Optional[str] = None
    draft_download_link: Optional[str] = None


class DraftListResponse(BaseModel):
    drafts: list[CaseInfo]
    total_drafts: int
