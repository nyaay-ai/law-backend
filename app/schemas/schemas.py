from typing import Any, Dict, Optional
from pydantic import BaseModel


# ── User ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str
    phone_number: str
    password: str
    preferred_language: Optional[str] = None
    language_for_draft: Optional[str] = None
    existing_document_prompt: Optional[str] = None
    user_other_details: Dict[str, Any] = {}


class UserRead(BaseModel):
    id: str
    name: str
    phone_number: Optional[str]
    preferred_language: Optional[str]
    language_for_draft: Optional[str]
    existing_document_prompt: Optional[str]
    user_other_details: Dict[str, Any]

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    phone_number: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Case ──────────────────────────────────────────────────────────────────────

from app.models.case import CaseOrderStatus, CaseDataStatus, FileStatus


class CaseCreate(BaseModel):
    case_external_data: Dict[str, Any] = {}
    case_internal_data: Dict[str, Any] = {}
    case_order_status: CaseOrderStatus = CaseOrderStatus.IN_PROGRESS
    case_data_status: CaseDataStatus = CaseDataStatus.PENDING
    file_status: FileStatus = FileStatus.DRAFT


class CaseUpdate(BaseModel):
    case_external_data: Optional[Dict[str, Any]] = None
    case_internal_data: Optional[Dict[str, Any]] = None
    case_order_status: Optional[CaseOrderStatus] = None
    case_data_status: Optional[CaseDataStatus] = None
    file_status: Optional[FileStatus] = None


class CaseRead(BaseModel):
    id: str
    case_external_data: Dict[str, Any]
    case_internal_data: Dict[str, Any]
    case_order_status: CaseOrderStatus
    case_data_status: CaseDataStatus
    file_status: FileStatus

    class Config:
        from_attributes = True


# ── CaseChat ──────────────────────────────────────────────────────────────────

from app.models.case_chat import ChatStatus


class CaseChatCreate(BaseModel):
    case_id: str
    raw_input: Optional[str] = None
    translated_input: Optional[str] = None
    whatsapp_chat_id: Optional[str] = None
    created_by: Optional[str] = None
    status: ChatStatus = ChatStatus.ACTIVE


class CaseChatRead(BaseModel):
    id: str
    case_id: str
    raw_input: Optional[str]
    translated_input: Optional[str]
    whatsapp_chat_id: Optional[str]
    created_by: Optional[str]
    status: ChatStatus

    class Config:
        from_attributes = True
