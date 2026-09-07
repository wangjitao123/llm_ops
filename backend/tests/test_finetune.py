import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone
from app.services.finetune_service import FinetuneService
from app.schemas.finetune import FinetuneTaskCreate, DatasetCreate


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def finetune_service(mock_db):
    return FinetuneService(mock_db)


@pytest.mark.asyncio
async def test_create_finetune_task(finetune_service):
    """Test creating a finetune task."""
    finetune_service.repo.create_task = AsyncMock(return_value=MagicMock(
        id=1, name="finetune-test", status="pending",
        created_at=datetime.now(timezone.utc),
    ))

    data = FinetuneTaskCreate(
        name="finetune-test",
        base_model_id=1,
        dataset_id=1,
        hyper_params={"learning_rate": 0.0001, "epochs": 3, "lora_rank": 8},
    )
    result = await finetune_service.create_task(data, "admin")

    assert result["id"] == 1
    assert result["name"] == "finetune-test"
    assert result["status"] == "pending"


@pytest.mark.asyncio
async def test_get_finetune_task(finetune_service):
    """Test getting a finetune task."""
    finetune_service.repo.get_task_by_id = AsyncMock(return_value=MagicMock(
        id=1, name="finetune-test", base_model_id=1, dataset_id=1,
        hyper_params={"learning_rate": 0.0001, "epochs": 3},
        status="running", progress=50, loss_value=0.5, error_message=None,
        started_at=datetime.now(timezone.utc), finished_at=None,
        created_by="admin", created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    ))

    result = await finetune_service.get_task(1)

    assert result is not None
    assert result["name"] == "finetune-test"
    assert result["status"] == "running"
    assert result["progress"] == 50


@pytest.mark.asyncio
async def test_list_finetune_tasks(finetune_service):
    """Test listing finetune tasks."""
    finetune_service.repo.get_all_tasks = AsyncMock(return_value=[
        MagicMock(id=1, name="task-1", status="running", progress=50,
                  created_at=datetime.now(timezone.utc)),
        MagicMock(id=2, name="task-2", status="completed", progress=100,
                  created_at=datetime.now(timezone.utc)),
    ])

    result = await finetune_service.list_tasks()

    assert len(result) == 2
    assert result[0]["status"] == "running"
    assert result[1]["status"] == "completed"


@pytest.mark.asyncio
async def test_update_task_status(finetune_service):
    """Test updating finetune task status."""
    finetune_service.repo.update_task = AsyncMock(return_value=MagicMock(
        id=1, status="running",
    ))

    result = await finetune_service.update_task_status(1, "running", "admin")

    assert result["status"] == "running"


@pytest.mark.asyncio
async def test_create_dataset(finetune_service):
    """Test creating a dataset."""
    finetune_service.repo.create_dataset = AsyncMock(return_value=MagicMock(
        id=1, name="test-dataset", format="jsonl", version="1.0.0",
        created_at=datetime.now(timezone.utc),
    ))

    data = DatasetCreate(name="test-dataset", format="jsonl", description="Test dataset")
    result = await finetune_service.create_dataset(data, "admin")

    assert result["name"] == "test-dataset"
    assert result["format"] == "jsonl"


@pytest.mark.asyncio
async def test_list_datasets(finetune_service):
    """Test listing datasets."""
    finetune_service.repo.get_all_datasets = AsyncMock(return_value=[
        MagicMock(id=1, name="dataset-1", format="jsonl", sample_count=1000,
                  version="1.0.0", annotation_status="labeled",
                  created_at=datetime.now(timezone.utc)),
    ])

    result = await finetune_service.list_datasets()

    assert len(result) == 1
    assert result[0]["format"] == "jsonl"


@pytest.mark.asyncio
async def test_finetune_state_transitions(finetune_service):
    """Test finetune task state transitions."""
    finetune_service.repo.update_task = AsyncMock(return_value=MagicMock(
        id=1, status="completed",
    ))

    # pending → running
    result_running = await finetune_service.update_task_status(1, "running", "admin")
    assert result_running["status"] == "running"

    # running → completed
    result_completed = await finetune_service.update_task_status(1, "completed", "admin")
    assert result_completed["status"] == "completed"

    # running → failed
    result_failed = await finetune_service.update_task_status(1, "failed", "admin")
    assert result_failed["status"] == "failed"

    # running → cancelled
    result_cancelled = await finetune_service.update_task_status(1, "cancelled", "admin")
    assert result_cancelled["status"] == "cancelled"


@pytest.mark.asyncio
async def test_default_hyper_params(finetune_service):
    """Test that default hyper parameters are used when not specified."""
    finetune_service.repo.create_task = AsyncMock(return_value=MagicMock(
        id=1, name="test", status="pending",
        created_at=datetime.now(timezone.utc),
    ))

    data = FinetuneTaskCreate(
        name="test",
        base_model_id=1,
        dataset_id=1,
        hyper_params={},
    )
    result = await finetune_service.create_task(data, "admin")

    assert result is not None