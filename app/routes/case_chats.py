from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.case_chat import CaseChat
from app.schemas.schemas import CaseChatCreate, CaseChatRead

router = APIRouter(prefix="/case-chats", tags=["case-chats"])


@router.post("", response_model=CaseChatRead, status_code=status.HTTP_201_CREATED)
async def create_chat(payload: CaseChatCreate, db: AsyncSession = Depends(get_db)):
    chat = await CaseChat.create(db, **payload.model_dump())
    return chat


@router.get("/by-case/{case_id}", response_model=List[CaseChatRead])
async def get_chats_by_case(case_id: str, active_only: bool = False, db: AsyncSession = Depends(get_db)):
    if active_only:
        return await CaseChat.get_active_by_case(db, case_id)
    return await CaseChat.get_by_case(db, case_id)


@router.get("/{chat_id}", response_model=CaseChatRead)
async def get_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    chat = await CaseChat.get_by_id(db, chat_id)
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return chat


@router.patch("/{chat_id}/deactivate", response_model=CaseChatRead)
async def deactivate_chat(chat_id: str, db: AsyncSession = Depends(get_db)):
    chat = await CaseChat.get_by_id(db, chat_id)
    if not chat:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat not found")
    return await chat.deactivate(db)
