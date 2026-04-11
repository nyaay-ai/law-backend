from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.case import Case
from app.schemas.schemas import CaseCreate, CaseRead, CaseUpdate

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post("", response_model=CaseRead, status_code=status.HTTP_201_CREATED)
async def create_case(payload: CaseCreate, db: AsyncSession = Depends(get_db)):
    case = await Case.create(db, **payload.model_dump())
    return case


@router.get("", response_model=List[CaseRead])
async def list_cases(db: AsyncSession = Depends(get_db)):
    return await Case.get_all(db)


@router.get("/{case_id}", response_model=CaseRead)
async def get_case(case_id: str, db: AsyncSession = Depends(get_db)):
    case = await Case.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    return case


@router.patch("/{case_id}", response_model=CaseRead)
async def update_case(case_id: str, payload: CaseUpdate, db: AsyncSession = Depends(get_db)):
    case = await Case.get_by_id(db, case_id)
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")
    updates = payload.model_dump(exclude_none=True)
    return await case.update(db, **updates)
