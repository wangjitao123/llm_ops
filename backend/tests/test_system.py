import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from tests.helpers import mock_orm
from datetime import datetime, timezone, date
from app.services.system_service import SystemService
from app.schemas.system import SystemConfigCreate, AlertRuleCreate


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def system_service(mock_db):
    return SystemService(mock_db)


@pytest.mark.asyncio
async def test_set_config_new(system_service):
    """Test creating a new system config."""
    system_service.repo.get_config = AsyncMock(return_value=None)
    system_service.repo.set_config = AsyncMock(return_value=mock_orm(
        config_key="sso.protocol", config_group="sso",
        updated_at=datetime.now(timezone.utc),
    ))

    data = SystemConfigCreate(
        config_key="sso.protocol",
        config_value="oauth2",
        config_group="sso",
        description="SSO authentication protocol",
    )
    result = await system_service.set_config(data, "admin")

    assert result["config_key"] == "sso.protocol"
    assert result["config_group"] == "sso"


@pytest.mark.asyncio
async def test_get_config(system_service):
    """Test getting a config value."""
    system_service.repo.get_config = AsyncMock(return_value=mock_orm(
        config_key="sso.protocol", config_value="oauth2", config_group="sso",
        description="SSO auth protocol",
    ))

    result = await system_service.get_config("sso.protocol")

    assert result is not None
    assert result["config_value"] == "oauth2"


@pytest.mark.asyncio
async def test_get_config_not_found(system_service):
    """Test getting a non-existent config."""
    system_service.repo.get_config = AsyncMock(return_value=None)

    result = await system_service.get_config("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_get_configs_by_group(system_service):
    """Test getting configs by group."""
    system_service.repo.get_configs_by_group = AsyncMock(return_value=[
        mock_orm(config_key="sso.protocol", config_value="oauth2", config_group="sso"),
        mock_orm(config_key="sso.authorize_url", config_value="https://sso.company.com/auth",
                  config_group="sso"),
    ])

    result = await system_service.get_configs_by_group("sso")

    assert len(result) == 2
    assert result[0]["config_group"] == "sso"


@pytest.mark.asyncio
async def test_create_alert_rule(system_service):
    """Test creating an alert rule."""
    system_service.repo.create_alert_rule = AsyncMock(return_value=mock_orm(
        id=1, name="Daily Token Alert", metric_type="daily_token",
        threshold_value=1000000, enabled=True,
        created_at=datetime.now(timezone.utc),
    ))

    data = AlertRuleCreate(
        name="Daily Token Alert",
        metric_type="daily_token",
        threshold_value=1000000,
        warn_at_percent=80,
    )
    result = await system_service.create_alert_rule(data, "admin")

    assert result["name"] == "Daily Token Alert"
    assert result["metric_type"] == "daily_token"
    assert result["threshold_value"] == 1000000


@pytest.mark.asyncio
async def test_list_alert_rules(system_service):
    """Test listing alert rules."""
    system_service.repo.get_alert_rules = AsyncMock(return_value=[
        mock_orm(id=1, name="Alert 1", metric_type="daily_token",
                  threshold_value=1000000, enabled=True,
                  created_at=datetime.now(timezone.utc)),
        mock_orm(id=2, name="Alert 2", metric_type="monthly_cost",
                  threshold_value=500000, enabled=True,
                  created_at=datetime.now(timezone.utc)),
    ])

    result = await system_service.list_alert_rules()

    assert len(result) == 2
    assert result[0]["metric_type"] == "daily_token"


@pytest.mark.asyncio
async def test_get_audit_logs(system_service):
    """Test getting audit logs with pagination."""
    system_service.repo.get_audit_logs = AsyncMock(return_value=[
        mock_orm(id=1, user_id="admin", action_type="key_create",
                  action_detail='{"key_name": "test"}', target_type="app_key",
                  target_id=1, client_ip="192.168.1.1", result="success",
                  created_at=datetime.now(timezone.utc)),
    ])

    result = await system_service.get_audit_logs(page=1, size=20)

    assert result["page"] == 1
    assert result["size"] == 20
    assert len(result["items"]) == 1
    assert result["items"][0]["action_type"] == "key_create"


@pytest.mark.asyncio
async def test_create_audit_log(system_service):
    """Test creating an audit log entry."""
    system_service.repo.create_audit_log = AsyncMock()

    await system_service.create_audit_log(
        user_id="admin",
        action_type="model_create",
        action_detail='{"model_name": "deepseek-v3"}',
        target_type="model",
        target_id=1,
        client_ip="192.168.1.1",
    )

    system_service.repo.create_audit_log.assert_called_once()


@pytest.mark.asyncio
async def test_alert_rule_different_metric_types(system_service):
    """Test creating alert rules with different metric types."""
    system_service.repo.create_alert_rule = AsyncMock(return_value=mock_orm(
        id=1, name="Test", metric_type="daily_token", threshold_value=1000, enabled=True,
        created_at=datetime.now(timezone.utc),
    ))

    metric_types = ["daily_token", "monthly_token", "daily_cost", "monthly_cost"]
    for mt in metric_types:
        data = AlertRuleCreate(name=f"{mt} alert", metric_type=mt, threshold_value=1000)
        result = await system_service.create_alert_rule(data, "admin")
        assert result is not None