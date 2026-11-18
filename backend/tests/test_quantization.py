"""测试量化任务 CRUD 和服务层。"""
import pytest
from unittest.mock import AsyncMock

from app.services.quantization_service import QuantizationService
from app.schemas.quantization import QuantizationTaskCreate
from tests.helpers import mock_orm


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def quant_service(mock_db):
    """量化服务实例。"""
    return QuantizationService(mock_db)


@pytest.mark.asyncio
async def test_create_task(quant_service):
    """创建量化任务应返回含 id 和基本信息的 dict。"""
    quant_service.repo.create = AsyncMock(return_value=mock_orm(
        id=1, name="测试量化", hf_model_id="Qwen/Qwen2.5-7B",
        algorithm="gptq", weight_bits=4, activation_bits=16,
        group_size=128, calib_samples=256, base_model_id=None,
        output_path=None, status="pending", progress=0,
        error_message=None, result_model_id=None,
        created_by="admin",
    ))

    data = QuantizationTaskCreate(
        name="测试量化",
        hf_model_id="Qwen/Qwen2.5-7B",
        algorithm="gptq",
        weight_bits=4,
    )
    result = await quant_service.create_task(data, "admin")

    assert result["name"] == "测试量化"
    assert result["hf_model_id"] == "Qwen/Qwen2.5-7B"
    assert result["algorithm"] == "gptq"
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_get_task_not_found(quant_service):
    """获取不存在的任务应返回 None。"""
    quant_service.repo.get_by_id = AsyncMock(return_value=None)
    result = await quant_service.get_task(999)
    assert result is None


@pytest.mark.asyncio
async def test_list_tasks(quant_service):
    """获取任务列表应返回 list[dict]。"""
    quant_service.repo.get_all = AsyncMock(return_value=[
        mock_orm(id=1, name="任务A", hf_model_id="Qwen/Qwen2.5-7B",
                 algorithm="gptq", weight_bits=4, activation_bits=16,
                 group_size=128, calib_samples=256, base_model_id=None,
                 output_path=None, status="pending", progress=0,
                 error_message=None, result_model_id=None,
                 created_by="admin",
                 created_at=__import__("datetime").datetime(2026, 1, 1, 0, 0, 0)),
        mock_orm(id=2, name="任务B", hf_model_id="meta-llama/Llama-2-7b",
                 algorithm="awq", weight_bits=4, activation_bits=16,
                 group_size=128, calib_samples=256, base_model_id=None,
                 output_path=None, status="completed", progress=100,
                 error_message=None, result_model_id=None,
                 created_by="admin",
                 created_at=__import__("datetime").datetime(2026, 1, 2, 0, 0, 0)),
    ])

    tasks = await quant_service.list_tasks()
    assert len(tasks) == 2
    assert tasks[0]["name"] == "任务A"
    assert tasks[1]["algorithm"] == "awq"


@pytest.mark.asyncio
async def test_update_task_status(quant_service):
    """更新任务状态应返回更新后的任务。"""
    quant_service.repo.update = AsyncMock(return_value=mock_orm(
        id=1, name="测试", hf_model_id="Qwen/Qwen2.5-7B",
        algorithm="gptq", weight_bits=4, activation_bits=16,
        group_size=128, calib_samples=256, base_model_id=None,
        output_path="/models/xxx", status="running", progress=50,
        error_message=None, result_model_id=None,
        created_by="admin",
    ))

    result = await quant_service.update_task(1, status="running", progress=50)
    assert result["status"] == "running"
    assert result["progress"] == 50


@pytest.mark.asyncio
async def test_delete_task(quant_service):
    """删除任务应委托 repo 并返回布尔值。"""
    quant_service.repo.delete = AsyncMock(return_value=True)
    assert await quant_service.delete_task(1) is True

    quant_service.repo.delete = AsyncMock(return_value=False)
    assert await quant_service.delete_task(999) is False


@pytest.mark.asyncio
async def test_submit_queues_task(quant_service, monkeypatch):
    """提交任务（pending 状态）应变为 queued。"""
    monkeypatch.setattr("app.tasks.quantization_runner.run_quantization.apply_async", lambda **kw: None)
    quant_service.repo.get_by_id = AsyncMock(return_value=mock_orm(
        id=1, name="测试", hf_model_id="Qwen/Qwen2.5-7B",
        algorithm="gptq", weight_bits=4, activation_bits=16,
        group_size=128, calib_samples=256, base_model_id=None,
        output_path=None, status="pending", progress=0,
        error_message=None, result_model_id=None,
        created_by="admin",
    ))
    quant_service.repo.update = AsyncMock(return_value=mock_orm(
        id=1, name="测试", hf_model_id="Qwen/Qwen2.5-7B",
        algorithm="gptq", weight_bits=4, activation_bits=16,
        group_size=128, calib_samples=256, base_model_id=None,
        output_path=None, status="queued", progress=0,
        error_message=None, result_model_id=None,
        created_by="admin",
    ))

    result = await quant_service.submit_quantization(1)
    assert result is not None
    assert result["status"] == "queued"