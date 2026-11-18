from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.schemas.common import ApiResponse
from app.schemas.perf import PerfTaskCreate, PerfTaskRerun
from app.services.perf_service import PerfService, PerfValidationError

router = APIRouter()


def _raise_perf_error(e: PerfValidationError) -> None:
    raise HTTPException(status_code=400, detail=str(e))


# ============================================================
# 注意：静态路径必须写在 /{task_id} 之前，
# 否则 "models" 会被当作 task_id 做 int 解析而报 422。
# ============================================================

@router.get("/models", response_model=ApiResponse)
async def list_testable_models(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """可压测的模型列表（已过滤：仅 provider 以 local- 开头的自建模型）。"""
    svc = PerfService(db)
    return ApiResponse(data=await svc.list_testable_models())


@router.get("/stats", response_model=ApiResponse)
async def perf_stats(
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """列表页顶部统计卡片。"""
    svc = PerfService(db)
    return ApiResponse(data=await svc.get_stats())


@router.post("/compare", response_model=ApiResponse)
async def compare_tasks(
    task_ids: list[int],
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """历史任务对比（2-4 个已完成任务）。"""
    svc = PerfService(db)
    try:
        result = await svc.compare_tasks(task_ids)
    except PerfValidationError as e:
        _raise_perf_error(e)
    return ApiResponse(data=result.model_dump())


@router.get("/tasks", response_model=ApiResponse)
async def list_perf_tasks(
    status_filter: Optional[str] = Query(None, alias="status"),
    model_id: Optional[int] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    svc = PerfService(db)
    tasks = await svc.list_tasks(status=status_filter, model_id=model_id, search=search)
    return ApiResponse(data=tasks)


@router.post("/tasks", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def create_perf_task(
    data: PerfTaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    svc = PerfService(db)
    try:
        result = await svc.create_task(data, current_user.get("sub", "system"))
    except PerfValidationError as e:
        _raise_perf_error(e)
    return ApiResponse(data=result)


@router.get("/tasks/{task_id}", response_model=ApiResponse)
async def get_perf_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    svc = PerfService(db)
    task = await svc.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="压测任务不存在")
    return ApiResponse(data=task)


@router.get("/tasks/{task_id}/logs", response_model=ApiResponse)
async def get_perf_task_logs(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    svc = PerfService(db)
    if not await svc.get_task(task_id):
        raise HTTPException(status_code=404, detail="压测任务不存在")
    return ApiResponse(data=await svc.get_logs(task_id))


@router.get("/tasks/{task_id}/engine-log", response_model=ApiResponse)
async def get_perf_engine_log(
    task_id: int,
    lines: int = Query(200, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """读取压测子进程的实时输出（EvalScope 进度条 / tokenizer 下载 / 异常堆栈）。

    压测卡住时用这个看它在干什么，不用进容器翻文件。
    """
    svc = PerfService(db)
    if not await svc.get_task(task_id):
        raise HTTPException(status_code=404, detail="压测任务不存在")
    return ApiResponse(data=await svc.get_engine_log(task_id, lines))


@router.get("/tasks/{task_id}/report")
async def download_perf_report(
    task_id: int,
    mode: str = Query(
        "summary",
        pattern="^(summary|full)$",
        description="summary=只有表格（默认，秒开）；full=含交互图表（需内联 4.5MB Plotly）",
    ),
    offline: bool = Query(True, description="full 模式下是否内联 Plotly（离线可看）"),
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """下载 EvalScope 原生 HTML 压测报告（Q-003 已确认保留并提供下载）。

    默认 **summary 模式**：原始报告要额外加载 4.5MB Plotly 并渲染 12 张 SVG，
    打开和滚动都很卡；而关键结论都在表格里。需要图表时传 `?mode=full`。
    """
    svc = PerfService(db)
    if not await svc.get_task(task_id):
        raise HTTPException(status_code=404, detail="压测任务不存在")
    path = await svc.get_report_path(task_id)
    if not path:
        raise HTTPException(
            status_code=404,
            detail="该任务没有可下载的报告（任务未完成，或报告目录已被清理）",
        )

    suffix = "" if mode == "full" else "_summary"
    filename = f"perf_report_{task_id}{suffix}.html"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    try:
        with open(path, encoding="utf-8") as f:
            html = f.read()
    except OSError:
        return FileResponse(path, media_type="text/html; charset=utf-8", filename=filename)

    from app.services.perf_report_assets import get_plotly_source, inline_plotly, strip_charts

    if mode == "summary":
        html, removed = strip_charts(html)
        headers["X-Report-Mode"] = "summary"
        headers["X-Report-Charts-Removed"] = str(removed)
        return HTMLResponse(content=html, media_type="text/html; charset=utf-8", headers=headers)

    if not offline:
        return FileResponse(path, media_type="text/html; charset=utf-8", filename=filename)

    plotly = await get_plotly_source()
    html, inlined = inline_plotly(html, plotly)
    headers["X-Report-Mode"] = "full"
    headers["X-Report-Offline"] = "true" if inlined else "false"
    return HTMLResponse(content=html, media_type="text/html; charset=utf-8", headers=headers)


@router.post("/tasks/{task_id}/cancel", response_model=ApiResponse)
async def cancel_perf_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """中止压测任务。"""
    svc = PerfService(db)
    if not await svc.get_task(task_id):
        raise HTTPException(status_code=404, detail="压测任务不存在")
    try:
        result = await svc.cancel_task(task_id)
    except PerfValidationError as e:
        _raise_perf_error(e)
    return ApiResponse(data=result)


@router.post("/tasks/{task_id}/rerun", response_model=ApiResponse, status_code=status.HTTP_201_CREATED)
async def rerun_perf_task(
    task_id: int,
    data: PerfTaskRerun,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """用相同参数重跑，创建新任务。"""
    svc = PerfService(db)
    try:
        result = await svc.rerun_task(task_id, data.name, current_user.get("sub", "system"))
    except PerfValidationError as e:
        _raise_perf_error(e)
    return ApiResponse(data=result)


@router.delete("/tasks/{task_id}", response_model=ApiResponse)
async def delete_perf_task(
    task_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    svc = PerfService(db)
    try:
        ok = await svc.delete_task(task_id)
    except PerfValidationError as e:
        _raise_perf_error(e)
    if not ok:
        raise HTTPException(status_code=404, detail="压测任务不存在")
    return ApiResponse(message="压测任务已删除")
