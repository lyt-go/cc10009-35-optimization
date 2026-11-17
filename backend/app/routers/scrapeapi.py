"""采集API接口：维护API定义，覆盖提交API评审、上线API、下线API等动作。

取数链路入口也在这里：执行API（缓存+限流+快照）、响应记录、缓存快照、
限流窗口四类只读查询，供运营核对某次响应来自缓存还是实际数据源。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.scrapeapi import ScrapeapiService
from app.services.scrapeapi_runtime import runtime

router = APIRouter(prefix="/api/scrapeapi", tags=["采集API"])

service = ScrapeapiService()

LIST_FIELDS = ["API编号", "API名称", "请求路径", "数据源绑定", "参数模板", "缓存策略", "速率限制", "返回格式"]
STATUSES = ["草稿", "API评审中", "已上线", "已下线"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按API编号检索"),
    status: str | None = Query(default=None, description="草稿、API评审中、已上线、已下线"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按API编号与状态过滤采集API列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/responses", response_model=PageResult[dict])
def list_responses(
    api_code: str | None = Query(default=None, description="按API编号过滤"),
    source: str | None = Query(default=None, description="按命中来源过滤：缓存命中、回源取数、冲突-新身份等"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """响应记录：每次取数的命中来源与额度消耗都可在这里核对。"""
    items, total = runtime.list_responses(api_code=api_code, source=source, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/cache", response_model=PageResult[dict])
def list_cache(
    api_code: str | None = Query(default=None, description="按API编号过滤"),
    page: int = 1,
    size: int = 50,
) -> PageResult[dict]:
    """缓存快照清单：缓存键含路径、参数指纹、数据源绑定与数据代际。"""
    items, total = runtime.list_cache(api_code=api_code, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/windows")
def list_windows(api_code: str | None = Query(default=None, description="按API编号过滤")) -> dict[str, Any]:
    """限流窗口计数：窗口内已用额度与扣减幂等键，解释额度消耗。"""
    items = runtime.list_windows(api_code=api_code)
    return {"module": "scrapeapi", "total": len(items), "items": items}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出采集API清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "scrapeapi", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条API定义明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"API定义 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条API定义，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="API定义已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条API定义执行提交API评审、上线API、下线API；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/execute")
def execute_entry(entry_id: int, payload: EntryPayload) -> dict[str, Any]:
    """执行一次采集API取数：限流计数 → 校验缓存键 → 命中或回源 → 生成快照与响应记录。

    入参 values.params 为请求参数，values.idempotency_key 为幂等键（可选，
    重复提交按幂等返回已保留结果，不重复扣减额度）。
    """
    params = payload.values.get("params")
    if params is not None and not isinstance(params, dict):
        raise HTTPException(status_code=400, detail="params 必须是键值对对象")
    idempotency_key = payload.values.get("idempotency_key")
    return runtime.execute(entry_id, params=params, idempotency_key=idempotency_key)
