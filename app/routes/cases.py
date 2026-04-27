from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.case import Case
from app.schemas.cases import CaseInfo, CaseListResponse, DraftInfo, DraftListResponse

router = APIRouter(prefix="/cases", tags=["cases"])


@router.get("/{user_id}", response_model=CaseListResponse)
async def get_case_list(user_id: str, db: AsyncSession = Depends(get_db)):
    target_status = ["IN_PROGRESS", "CLOSED"]
    filters = {"user_id": user_id, "case_order_status": target_status}
    cases = await Case.filter_by(db, **filters)

    if not cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )

    cases_list = []

    for case in cases:
        case_info = CaseInfo(
            case_id=case.id,
            case_name=case.case_external_data.get("case_name", ""),
            court_name=case.case_external_data.get("court_name", ""),
            filing_date=case.case_external_data.get("filing_date"),
            last_hearing_date=case.case_external_data.get("last_hearing_date"),
            next_hearing_date=case.case_external_data.get("next_hearing_date"),
            advocate_name=case.case_external_data.get("advocate_name"),
            case_number=case.case_external_data.get("case_number"),
            case_status=case.case_order_status.value,
            case_type=case.case_external_data.get("case_type"),
            notes=case.case_internal_data.get("notes"),
        )
        cases_list.append(case_info)

    return CaseListResponse(
        cases=cases,
        total_cases=len(cases),
        active_cases=sum(1 for case in cases if case.case_status == "active"),
        closed_cases=sum(1 for case in cases if case.case_status == "closed"),
    )


@router.get("/drafts/{user_id}", response_model=DraftListResponse)
async def get_drafts_list(user_id: str, db: AsyncSession = Depends(get_db)):
    target_status = ["DRAFT"]
    filters = {"user_id": user_id, "case_order_status": target_status}
    cases = await Case.filter_by(db, **filters)

    if not cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Case not found"
        )

    drafts_list = []

    for case in cases:
        case_info = DraftInfo(
            case_id=case.id,
            draft_name=case.case_internal_data.get("draft_name", ""),
            court_name=case.case_internal_data.get("court_name", ""),
            case_type=case.case_internal_data.get("case_type"),
            created_at=case.created_at.isoformat(),
            draft_download_link="",
        )
        drafts_list.append(case_info)

    return DraftListResponse(
        drafts=drafts_list,
        total_drafts=len(drafts_list),
    )
