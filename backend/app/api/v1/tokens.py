from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.services.token_service import TokenService
from app.schemas.token import TokenStatsQuery, CostReportQuery
from app.schemas.common import ApiResponse

router = APIRouter()


@router.get("/stats", response_model=ApiResponse)
async def get_token_stats(
    dimension_type: str,
    dimension_id: int = None,
    start_date: str = None,
    end_date: str = None,
    granularity: str = "daily",
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from datetime import date
    if not start_date:
        from datetime import timedelta
        start_date = (date.today() - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = date.today().isoformat()
    
    service = TokenService(db)
    result = await service.get_stats(
        dimension_type, dimension_id,
        date.fromisoformat(start_date), date.fromisoformat(end_date),
        granularity,
    )
    return ApiResponse(data=result)


@router.get("/summary", response_model=ApiResponse)
async def get_token_summary(
    start_date: str = None,
    end_date: str = None,
    dimension_type: str = "model",
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from datetime import date, timedelta
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = date.today().isoformat()
    
    service = TokenService(db)
    result = await service.get_summary(
        date.fromisoformat(start_date), date.fromisoformat(end_date), dimension_type,
    )
    return ApiResponse(data=result)


@router.get("/cost-report", response_model=ApiResponse)
async def get_cost_report(
    start_date: str = None,
    end_date: str = None,
    group_by: str = "model",
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from datetime import date, timedelta
    if not start_date:
        start_date = (date.today() - timedelta(days=30)).isoformat()
    if not end_date:
        end_date = date.today().isoformat()
    
    service = TokenService(db)
    result = await service.get_cost_report(
        date.fromisoformat(start_date), date.fromisoformat(end_date), group_by,
    )
    return ApiResponse(data=result)