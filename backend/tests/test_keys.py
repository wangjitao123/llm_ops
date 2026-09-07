import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from tests.helpers import mock_orm
from datetime import datetime, timezone
from app.services.key_service import KeyService, ApplicationService
from app.schemas.key import KeyCreate, KeyUpdate


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def key_service(mock_db):
    return KeyService(mock_db)


@pytest.mark.asyncio
async def test_create_key(key_service):
    """Test creating a new API key with model permissions."""
    key_service.repo.create_key = AsyncMock(return_value=mock_orm(
        id=1, name="test-key", key_prefix="sk-a1b2c3", status="active",
        created_at=datetime.now(timezone.utc),
    ))
    key_service.repo.set_model_permissions = AsyncMock()

    data = KeyCreate(
        name="test-key",
        application_id=1,
        model_ids=[1, 2],
        qps_limit=100,
    )
    result = await key_service.create_key(data, "admin")

    assert result["id"] == 1
    assert result["name"] == "test-key"
    assert result["key_full"].startswith("sk-")
    assert result["status"] == "active"
    key_service.repo.set_model_permissions.assert_called_once_with(1, [1, 2])


@pytest.mark.asyncio
async def test_get_key_found(key_service):
    """Test getting a key by ID."""
    key_service.repo.get_by_id = AsyncMock(return_value=mock_orm(
        id=1, name="test-key", key_prefix="sk-a1b2c3", status="active",
        application_id=1, qps_limit=100, rpm_limit=6000, rpd_limit=100000,
        token_quota=1000000, token_used=5000, expires_at=None, last_used_at=None,
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    ))

    result = await key_service.get_key(1)

    assert result is not None
    assert result["name"] == "test-key"
    assert result["status"] == "active"


@pytest.mark.asyncio
async def test_get_key_not_found(key_service):
    """Test getting a key that doesn't exist."""
    key_service.repo.get_by_id = AsyncMock(return_value=None)

    result = await key_service.get_key(999)

    assert result is None


@pytest.mark.asyncio
async def test_list_keys(key_service):
    """Test listing all keys."""
    key_service.repo.get_all = AsyncMock(return_value=[
        mock_orm(id=1, name="key-1", key_prefix="sk-a1", status="active",
                  created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)),
        mock_orm(id=2, name="key-2", key_prefix="sk-b2", status="disabled",
                  created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)),
    ])

    result = await key_service.list_keys()

    assert len(result) == 2
    assert result[0]["name"] == "key-1"


@pytest.mark.asyncio
async def test_update_key(key_service):
    """Test updating a key."""
    key_service.repo.update_key = AsyncMock(return_value=mock_orm(
        id=1, name="test-key-updated", key_prefix="sk-a1", status="disabled",
        created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc),
    ))

    data = KeyUpdate(name="test-key-updated", status="disabled")
    result = await key_service.update_key(1, data, "admin")

    assert result is not None
    assert result["name"] == "test-key-updated"
    assert result["status"] == "disabled"


@pytest.mark.asyncio
async def test_delete_key(key_service):
    """Test deleting a key."""
    key_service.repo.get_by_id = AsyncMock(return_value=mock_orm(id=1))
    key_service.repo.delete_key = AsyncMock()

    result = await key_service.delete_key(1)

    assert result is True
    key_service.repo.delete_key.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_verify_key_valid(key_service):
    """Test verifying a valid active key."""
    key_service.repo.get_by_key_hash = AsyncMock(return_value=mock_orm(
        id=1, status="active", qps_limit=100, token_quota=1000000, deleted_at=None,
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
    ))

    result = await key_service.verify_key("valid-hash")

    assert result is not None
    assert result["id"] == 1


@pytest.mark.asyncio
async def test_verify_key_invalid(key_service):
    """Test verifying an invalid key."""
    key_service.repo.get_by_key_hash = AsyncMock(return_value=None)

    result = await key_service.verify_key("invalid-hash")

    assert result is None


@pytest.mark.asyncio
async def test_verify_key_expired(key_service):
    """Test verifying an expired key."""
    key_service.repo.get_by_key_hash = AsyncMock(return_value=mock_orm(
        id=1, status="active", qps_limit=100, token_quota=1000000, deleted_at=None,
        expires_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
    ))
    key_service.repo.update_key = AsyncMock()

    result = await key_service.verify_key("expired-hash")

    assert result is None
    key_service.repo.update_key.assert_called_once()


@pytest.mark.asyncio
async def test_key_generation_format(key_service):
    """Test that generated keys have correct format."""
    data = KeyCreate(name="format-test")
    key_service.repo.create_key = AsyncMock(return_value=mock_orm(
        id=10, name="format-test", key_prefix="sk-", status="active",
        created_at=datetime.now(timezone.utc),
    ))

    result = await key_service.create_key(data, "admin")

    assert result["key_full"].startswith("sk-")
    assert len(result["key_full"]) > 10