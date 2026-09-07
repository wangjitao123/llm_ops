import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from tests.helpers import mock_orm
from datetime import datetime, timezone, date, timedelta
from app.services.model_service import ModelService
from app.schemas.model import ModelCreate, ModelUpdate, ModelStatusUpdate


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def model_service(mock_db):
    return ModelService(mock_db)


@pytest.mark.asyncio
async def test_create_model(model_service, mock_db):
    """Test creating a new model."""
    mock_db.flush = AsyncMock()
    model_service.repo.create = AsyncMock(return_value=mock_orm(
        id=1, name="deepseek-v3", version="1.0.0"
    ))
    model_service.repo.create_version = AsyncMock(return_value=mock_orm())

    data = ModelCreate(
        name="deepseek-v3",
        provider="deepseek",
        api_base_url="https://api.deepseek.com/v1",
        api_key="sk-test-key",
        qps_limit=100,
        timeout_ms=60000,
        weight=1,
    )
    result = await model_service.create_model(data, "admin")

    assert result["id"] == 1
    assert result["name"] == "deepseek-v3"
    assert result["version"] == "1.0.0"
    model_service.repo.create.assert_called_once()
    model_service.repo.create_version.assert_called_once()


@pytest.mark.asyncio
async def test_get_model_found(model_service):
    """Test getting a model by ID when it exists."""
    mock_model = mock_orm(
        id=1, name="deepseek-v3", provider="deepseek", version="1.0.0",
        api_base_url="https://api.deepseek.com/v1", qps_limit=100, timeout_ms=60000,
        weight=1, status="online", health_check_url=None, model_config=None,
        description=None, created_by="admin",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    )
    model_service.repo.get_by_id = AsyncMock(return_value=mock_model)

    result = await model_service.get_model(1)

    assert result is not None
    assert result["name"] == "deepseek-v3"
    assert result["status"] == "online"


@pytest.mark.asyncio
async def test_get_model_not_found(model_service):
    """Test getting a model by ID when it doesn't exist."""
    model_service.repo.get_by_id = AsyncMock(return_value=None)

    result = await model_service.get_model(999)

    assert result is None


@pytest.mark.asyncio
async def test_list_models(model_service):
    """Test listing all models."""
    mock_models = [
        mock_orm(id=1, name="gpt-4o", provider="openai", version="1.0.0",
                  api_base_url="https://api.openai.com/v1", qps_limit=100, timeout_ms=60000,
                  weight=1, status="online", health_check_url=None, model_config=None,
                  description=None, created_by="admin",
                  created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)),
        mock_orm(id=2, name="deepseek-v3", provider="deepseek", version="1.0.0",
                  api_base_url="https://api.deepseek.com/v1", qps_limit=100, timeout_ms=60000,
                  weight=1, status="online", health_check_url=None, model_config=None,
                  description=None, created_by="admin",
                  created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)),
    ]
    model_service.repo.get_all = AsyncMock(return_value=mock_models)

    result = await model_service.list_models()

    assert len(result) == 2
    assert result[0]["name"] == "gpt-4o"
    assert result[1]["provider"] == "deepseek"


@pytest.mark.asyncio
async def test_update_model(model_service):
    """Test updating a model."""
    model_service.repo.get_by_id = AsyncMock(return_value=mock_orm(id=1, version="1.0.0"))
    model_service.repo.update = AsyncMock(return_value=mock_orm(
        id=1, name="deepseek-v3-updated", provider="deepseek", version="1.1.0",
        api_base_url="https://api.deepseek.com/v1", qps_limit=200, timeout_ms=60000,
        weight=1, status="online",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    ))
    model_service.repo.create_version = AsyncMock(return_value=mock_orm())

    data = ModelUpdate(qps_limit=200)
    result = await model_service.update_model(1, data, "admin")

    assert result is not None
    assert result["qps_limit"] == 200


@pytest.mark.asyncio
async def test_delete_model_success(model_service):
    """Test deleting a model successfully."""
    model_service.repo.get_by_id = AsyncMock(return_value=mock_orm(id=1))
    model_service.repo.delete = AsyncMock()

    result = await model_service.delete_model(1)

    assert result is True
    model_service.repo.delete.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_delete_model_not_found(model_service):
    """Test deleting a model that doesn't exist."""
    model_service.repo.get_by_id = AsyncMock(return_value=None)

    result = await model_service.delete_model(999)

    assert result is False


@pytest.mark.asyncio
async def test_update_status(model_service):
    """Test updating model status."""
    model_service.repo.update = AsyncMock(return_value=mock_orm(
        id=1, name="deepseek-v3", status="offline",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    ))

    result = await model_service.update_status(1, "offline", "admin")

    assert result is not None
    assert result["status"] == "offline"


@pytest.mark.asyncio
async def test_get_versions(model_service):
    """Test getting model versions."""
    model_service.repo.get_versions = AsyncMock(return_value=[
        mock_orm(id=1, version="1.0.0", is_current=True, change_log="Initial version",
                  created_at=datetime.now(timezone.utc)),
        mock_orm(id=2, version="1.1.0", is_current=False, change_log="Updated config",
                  created_at=datetime.now(timezone.utc)),
    ])

    result = await model_service.get_versions(1)

    assert len(result) == 2
    assert result[0]["version"] == "1.0.0"
    assert result[0]["is_current"] is True