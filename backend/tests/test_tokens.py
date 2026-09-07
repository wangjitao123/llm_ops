import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from tests.helpers import mock_orm
from datetime import date, datetime, timezone, timedelta
from app.services.token_service import TokenService


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def token_service(mock_db):
    return TokenService(mock_db)


@pytest.mark.asyncio
async def test_get_daily_stats(token_service):
    """Test getting daily token statistics."""
    mock_stats = [
        mock_orm(stats_date=date(2025, 1, 1), prompt_tokens=1000, completion_tokens=500,
                  total_tokens=1500, request_count=100, total_cost=0.015),
        mock_orm(stats_date=date(2025, 1, 2), prompt_tokens=2000, completion_tokens=1000,
                  total_tokens=3000, request_count=200, total_cost=0.030),
    ]
    token_service.repo.get_daily_stats = AsyncMock(return_value=mock_stats)

    result = await token_service.get_stats(
        "model", 1, date(2025, 1, 1), date(2025, 1, 7), "daily"
    )

    assert result["dimension_type"] == "model"
    assert result["dimension_id"] == 1
    assert len(result["points"]) == 2
    assert result["total_tokens"] == 4500
    assert result["total_cost"] == 0.045


@pytest.mark.asyncio
async def test_get_hourly_stats(token_service):
    """Test getting hourly token statistics."""
    mock_stats = [
        mock_orm(stats_date=date(2025, 1, 1), stats_hour=10,
                  prompt_tokens=500, completion_tokens=250,
                  total_tokens=750, request_count=50, total_cost=0.0075),
        mock_orm(stats_date=date(2025, 1, 1), stats_hour=11,
                  prompt_tokens=800, completion_tokens=400,
                  total_tokens=1200, request_count=80, total_cost=0.012),
    ]
    token_service.repo.get_hourly_stats = AsyncMock(return_value=mock_stats)

    result = await token_service.get_stats(
        "model", 1, date(2025, 1, 1), date(2025, 1, 1), "hourly"
    )

    assert len(result["points"]) == 2
    assert "10:00" in result["points"][0]["date"]
    assert result["total_tokens"] == 1950


@pytest.mark.asyncio
async def test_get_stats_empty(token_service):
    """Test getting stats when no data exists."""
    token_service.repo.get_daily_stats = AsyncMock(return_value=[])

    result = await token_service.get_stats(
        "model", 999, date(2025, 1, 1), date(2025, 1, 7), "daily"
    )

    assert len(result["points"]) == 0
    assert result["total_tokens"] == 0
    assert result["total_cost"] == 0


@pytest.mark.asyncio
async def test_get_summary(token_service):
    """Test getting summary statistics."""
    token_service.repo.get_summary = AsyncMock(return_value=[
        {"dimension_id": 1, "total_tokens": 10000, "total_cost": 0.1, "request_count": 500},
        {"dimension_id": 2, "total_tokens": 20000, "total_cost": 0.2, "request_count": 1000},
    ])

    result = await token_service.get_summary(
        date(2025, 1, 1), date(2025, 1, 31), "model"
    )

    assert len(result) == 2
    assert result[0]["total_tokens"] == 10000


@pytest.mark.asyncio
async def test_get_cost_report(token_service):
    """Test getting cost report."""
    token_service.repo.get_summary = AsyncMock(return_value=[
        {"dimension_id": 1, "total_tokens": 10000, "total_cost": 0.1, "request_count": 500},
    ])

    result = await token_service.get_cost_report(
        date(2025, 1, 1), date(2025, 1, 31), "model"
    )

    assert result["group_by"] == "model"
    assert result["total_cost"] == 0.1
    assert result["total_tokens"] == 10000
    assert len(result["items"]) == 1


@pytest.mark.asyncio
async def test_stats_with_different_dimensions(token_service):
    """Test stats with different dimension types."""
    token_service.repo.get_daily_stats = AsyncMock(return_value=[
        mock_orm(stats_date=date(2025, 1, 1), prompt_tokens=100, completion_tokens=50,
                  total_tokens=150, request_count=10, total_cost=0.0015),
    ])

    # Test by application
    result_app = await token_service.get_stats(
        "application", 1, date(2025, 1, 1), date(2025, 1, 1), "daily"
    )
    assert result_app["dimension_type"] == "application"

    # Test by user
    result_user = await token_service.get_stats(
        "user", "user123", date(2025, 1, 1), date(2025, 1, 1), "daily"
    )
    assert result_user["dimension_type"] == "user"

    # Test by key
    result_key = await token_service.get_stats(
        "key", 1, date(2025, 1, 1), date(2025, 1, 1), "daily"
    )
    assert result_key["dimension_type"] == "key"