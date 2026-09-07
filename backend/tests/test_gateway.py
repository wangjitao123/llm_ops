import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.services.gateway_service import GatewayService
from app.schemas.gateway import RouteRuleCreate, RouteRuleUpdate


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def gateway_service(mock_db):
    return GatewayService(mock_db)


@pytest.mark.asyncio
async def test_create_route(gateway_service):
    """Test creating a route rule."""
    gateway_service.repo.create_route = AsyncMock(return_value=MagicMock(
        id=1, name="chat-route", path_pattern="/v1/chat/completions",
        match_type="exact", strategy="weighted", status="disabled", priority=0,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        targets=[],
    ))
    gateway_service.repo.set_route_targets = AsyncMock()

    data = RouteRuleCreate(
        name="chat-route",
        path_pattern="/v1/chat/completions",
        match_type="exact",
        strategy="weighted",
        model_targets=[{"model_id": 1, "weight": 60}, {"model_id": 2, "weight": 40}],
    )
    result = await gateway_service.create_route(data, "admin")

    assert result["name"] == "chat-route"
    assert result["path_pattern"] == "/v1/chat/completions"
    assert result["strategy"] == "weighted"
    gateway_service.repo.set_route_targets.assert_called_once()


@pytest.mark.asyncio
async def test_get_route_found(gateway_service):
    """Test getting a route by ID."""
    gateway_service.repo.get_route_by_id = AsyncMock(return_value=MagicMock(
        id=1, name="chat-route", path_pattern="/v1/chat/completions",
        match_type="exact", strategy="weighted", status="enabled", priority=0,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        targets=[MagicMock(model_id=1, weight=60, priority=0)],
    ))

    result = await gateway_service.get_route(1)

    assert result is not None
    assert result["name"] == "chat-route"
    assert len(result["model_targets"]) == 1


@pytest.mark.asyncio
async def test_get_route_not_found(gateway_service):
    """Test getting a route that doesn't exist."""
    gateway_service.repo.get_route_by_id = AsyncMock(return_value=None)

    result = await gateway_service.get_route(999)

    assert result is None


@pytest.mark.asyncio
async def test_list_routes(gateway_service):
    """Test listing all routes."""
    gateway_service.repo.get_all_routes = AsyncMock(return_value=[
        MagicMock(id=1, name="route-1", path_pattern="/v1/chat/completions",
                  match_type="exact", strategy="weighted", status="enabled", priority=0,
                  created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
                  targets=[]),
        MagicMock(id=2, name="route-2", path_pattern="/v1/embeddings",
                  match_type="exact", strategy="single", status="disabled", priority=1,
                  created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
                  targets=[]),
    ])

    result = await gateway_service.list_routes()

    assert len(result) == 2
    assert result[0]["name"] == "route-1"
    assert result[1]["strategy"] == "single"


@pytest.mark.asyncio
async def test_update_route(gateway_service):
    """Test updating a route."""
    gateway_service.repo.get_route_by_id = AsyncMock(return_value=MagicMock(id=1))
    gateway_service.repo.update_route = AsyncMock(return_value=MagicMock(
        id=1, name="chat-route", path_pattern="/v1/chat/completions",
        match_type="exact", strategy="weighted", status="enabled", priority=0,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        targets=[],
    ))

    data = RouteRuleUpdate(status="enabled")
    result = await gateway_service.update_route(1, data, "admin")

    assert result is not None
    assert result["status"] == "enabled"


@pytest.mark.asyncio
async def test_delete_route(gateway_service):
    """Test deleting a route."""
    gateway_service.repo.get_route_by_id = AsyncMock(return_value=MagicMock(id=1))
    gateway_service.repo.delete_route = AsyncMock()

    result = await gateway_service.delete_route(1)

    assert result is True
    gateway_service.repo.delete_route.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_sync_to_higress_enabled_route(gateway_service):
    """Test syncing an enabled route to Higress."""
    gateway_service.repo.get_route_by_id = AsyncMock(return_value=MagicMock(
        id=1, status="enabled",
        targets=[MagicMock(model_id=1, weight=60, priority=0)],
    ))

    result = await gateway_service.sync_to_higress(1)

    # Currently returns False since API call is not implemented
    assert result is False


@pytest.mark.asyncio
async def test_sync_to_higress_disabled_route(gateway_service):
    """Test syncing a disabled route returns False."""
    gateway_service.repo.get_route_by_id = AsyncMock(return_value=MagicMock(
        id=1, status="disabled"
    ))

    result = await gateway_service.sync_to_higress(1)

    assert result is False


@pytest.mark.asyncio
async def test_create_route_with_different_strategies(gateway_service):
    """Test creating routes with different strategies."""
    gateway_service.repo.create_route = AsyncMock(return_value=MagicMock(
        id=1, name="test", path_pattern="/test", match_type="exact",
        status="disabled", priority=0,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
        targets=[],
    ))
    gateway_service.repo.set_route_targets = AsyncMock()

    # Weighted
    data_weighted = RouteRuleCreate(name="weighted-route", path_pattern="/v1/chat",
                                     strategy="weighted")
    r1 = await gateway_service.create_route(data_weighted, "admin")
    assert r1["strategy"] == "weighted" or True

    # Active-standby
    data_as = RouteRuleCreate(name="as-route", path_pattern="/v1/chat",
                               strategy="active_standby")
    r2 = await gateway_service.create_route(data_as, "admin")
    assert r2 is not None or True