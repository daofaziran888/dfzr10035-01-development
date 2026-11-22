"""批次交接分布视图与重放本轮取单接口：独立于通用资源路由，挂在 /api 下。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.batch_handover import BatchHandoverService
from app.services.retry_queue import RetryQueueService

router = APIRouter(prefix="/api", tags=["批次交接"])

handover_service = BatchHandoverService()


class SkipPayload(BaseModel):
    remark: str | None = None


@router.get("/request_batch/handover/summary")
def handover_summary() -> dict:
    """按批次列出尚未收齐的请求，交接时先在这里挑批次。"""
    return {"items": handover_service.summary()}


@router.get("/request_batch/{batch_id}/handover")
def handover_distribution(batch_id: int) -> dict:
    """批次请求结果分布视图：统计按逻辑请求去重，可展开到原请求。"""
    payload, message = handover_service.distribution(batch_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=message)
    return payload


@router.get("/request_batch/requests/{request_id}")
def handover_request_detail(request_id: int) -> dict:
    """单条请求的尝试明细：各次回执 + 交接变迁。"""
    payload, message = handover_service.detail(request_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=message)
    return payload


@router.post("/request_batch/{batch_id}/sync")
def handover_sync_batch(batch_id: int) -> dict:
    """同步该批新到回执，返回本次观察相对上次的变化。"""
    payload, message = handover_service.sync_batch(batch_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=message)
    return {"ok": True, "message": message, **payload}


@router.post("/request_batch/requests/{request_id}/sync")
def handover_sync_request(request_id: int) -> dict:
    """展开请求时同步它的在途回执。"""
    payload, message = handover_service.sync_request(request_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=message)
    return {"ok": True, "message": message, **payload}


@router.post("/request_batch/requests/{request_id}/dispatch")
def handover_dispatch_request(request_id: int) -> dict:
    """值班员从分布视图把该请求派发补采。"""
    payload, message = handover_service.dispatch(request_id)
    return {"ok": payload is not None, "message": message, **(payload or {})}


@router.post("/request_batch/{batch_id}/dispatch")
def handover_dispatch_batch(batch_id: int) -> dict:
    """把该批尚未收齐的请求全部派发补采。"""
    payload, message = handover_service.dispatch_batch(batch_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=message)
    return {"ok": True, "message": message, **payload}


@router.post("/request_batch/requests/{request_id}/skip")
def handover_skip_request(request_id: int, payload: SkipPayload | None = None) -> dict:
    """值班员确认跳过补采，记录依据回执。"""
    remark = payload.remark if payload else None
    result, message = handover_service.skip(request_id, remark)
    return {"ok": result is not None, "message": message, **(result or {})}


@router.get("/retry_queue/round/current")
def retry_round_current() -> dict:
    """重放队列本轮取单视图：可取单、被交接跳过、已确认请求。"""
    return RetryQueueService().current_round()
