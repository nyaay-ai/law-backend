from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.engine import InputProcessingEngine
from app.schemas import InputProcessingPayload, InputProcessingResponse
from app.schemas.schemas import ReferencePayload, ReferenceRetrievalResponse

router = APIRouter(prefix="/engine", tags=["engine"])


@router.post(
    "/input-process",
    response_model=InputProcessingResponse,
    status_code=status.HTTP_200_OK,
)
async def inputProcessing(
    payload: InputProcessingPayload, db: AsyncSession = Depends(get_db)
):
    # existing = await User.get_by_phone(db, payload.phone_number)
    # if existing:
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail="Phone number already registered",
    #     )
    # user = await User.create(
    #     db, **payload.model_dump(exclude={"password"}), password=payload.password
    # )
    # return user

    print("Received payload:", payload)
    engine = InputProcessingEngine()
    response = await engine.classification(
        db,
        payload.case_id,
        payload.translated_text,
        payload.original_text,
        payload.missing_fields_answers,
    )

    if (response.get("follow_up_questions") or []) and len(
        response["follow_up_questions"]
    ) > 0:
        return {
            "message": "Input processed with missing fields",
            "missing_fields": response["follow_up_questions"],
        }

    return {"message": "Input processed successfully", "missing_fields": []}


@router.post(
    "/reference-retrieval",
    response_model=ReferenceRetrievalResponse,
    status_code=status.HTTP_200_OK,
)
async def referenceRetrieval(
    payload: ReferencePayload, db: AsyncSession = Depends(get_db)
):
    # existing = await User.get_by_phone(db, payload.phone_number)
    # if existing:
    #     raise HTTPException(
    #         status_code=status.HTTP_409_CONFLICT,
    #         detail="Phone number already registered",
    #     )
    # user = await User.create(
    #     db, **payload.model_dump(exclude={"password"}), password=payload.password
    # )
    # return user

    print("Received payload:", payload)
    engine = InputProcessingEngine()
    # response = await engine.classification(
    #     db,
    #     payload.case_id,
    #     payload.translated_text,
    #     payload.original_text,
    #     payload.missing_fields_answers,
    # )

    response = await engine.test_reference_retrieval(payload.fields)

    if (response.get("follow_up_questions") or []) and len(
        response["follow_up_questions"]
    ) > 0:
        return {
            "message": "Input processed with missing fields",
            "missing_fields": response["follow_up_questions"],
        }

    return {"message": "Input processed successfully", "missing_fields": []}
