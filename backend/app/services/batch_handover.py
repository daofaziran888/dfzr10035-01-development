"""批次交接领域服务：把批次调用记录与重放回执关联到同一条逻辑采集请求上。

约定：
- 每个逻辑请求（请求编号）在交接统计里只占一个位置，它的各次尝试（回执）挂在其下；
- 参数相同的独立请求是不同的逻辑请求，分别计入统计；
- 同一请求在原批次和后续重放中可能各有一份回执，确认回执取尝试序号最大的已到达回执；
- 派发补采 / 跳过补采 / 重放结果回写 / 重放队列本轮取单，读写的是同一份交接状态；
- 每次状态变化都写交接变迁，值班员据此解释前后两次观察为何不同。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

REQUEST_TABLE = "_batch_request"
RECEIPT_TABLE = "_receipt"
EVENT_TABLE = "_handover_event"

# 尚未收齐：交接上还不能算办结的状态
INCOMPLETE_STATES = ("待回执", "失败待补采", "补采中")
# 重放队列里仍在占用取单名额的任务状态
ACTIVE_TASK_STATUS = ("待重试", "重试中")


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _next_id(rows: list[dict[str, Any]]) -> int:
    return max((int(r.get("id", 0)) for r in rows), default=0) + 1


def _receipt_sort_key(receipt: dict[str, Any]) -> tuple[int, int]:
    return (int(receipt.get("尝试序号", 0)), int(receipt.get("id", 0)))


class BatchHandoverService:
    """批次请求结果分布视图与交接清单的领域逻辑。"""

    # ---------- 基础查询 ----------

    def list_requests(self, batch_code: str | None = None) -> list[dict[str, Any]]:
        rows = list(store.rows(REQUEST_TABLE))
        if batch_code:
            rows = [row for row in rows if row.get("批次编号") == batch_code]
        return rows

    def find_request(self, request_id: int) -> dict[str, Any] | None:
        for row in store.rows(REQUEST_TABLE):
            if int(row.get("id", 0)) == request_id:
                return row
        return None

    def find_request_by_code(self, code: str) -> dict[str, Any] | None:
        if not code:
            return None
        for row in store.rows(REQUEST_TABLE):
            if row.get("请求编号") == code:
                return row
        return None

    def find_receipt(self, code: str) -> dict[str, Any] | None:
        if not code:
            return None
        for row in store.rows(RECEIPT_TABLE):
            if row.get("回执编号") == code:
                return row
        return None

    def receipts_of(self, code: str, *, arrived_only: bool = False) -> list[dict[str, Any]]:
        rows = [r for r in store.rows(RECEIPT_TABLE) if r.get("请求编号") == code]
        if arrived_only:
            rows = [r for r in rows if r.get("到达状态") == "已到达"]
        return sorted(rows, key=_receipt_sort_key)

    def events_of(self, code: str) -> list[dict[str, Any]]:
        return [e for e in store.rows(EVENT_TABLE) if e.get("请求编号") == code]

    def active_task_of(self, code: str) -> dict[str, Any] | None:
        for task in store.rows("retry_queue"):
            if task.get("关联请求编号") == code and task.get("status") in ACTIVE_TASK_STATUS:
                return task
        return None

    # ---------- 状态推导 ----------

    def request_state(self, req: dict[str, Any]) -> str:
        """逻辑请求的交接状态：成功 / 失败待补采 / 补采中 / 待回执 / 已跳过。"""
        if req.get("处置方式") == "跳过":
            return "已跳过"
        receipt = self.find_receipt(str(req.get("确认回执", "")))
        if receipt is not None:
            if receipt.get("结果") == "成功":
                return "成功"
            if self.active_task_of(str(req.get("请求编号", ""))) is not None:
                return "补采中"
            return "失败待补采"
        if self.active_task_of(str(req.get("请求编号", ""))) is not None:
            return "补采中"
        return "待回执"

    def _present_request(self, req: dict[str, Any]) -> dict[str, Any]:
        receipts = self.receipts_of(str(req.get("请求编号", "")))
        arrived = [r for r in receipts if r.get("到达状态") == "已到达"]
        presented = dict(req)
        presented["当前结果"] = self.request_state(req)
        presented["尝试次数"] = len(arrived)
        presented["在途回执数"] = len(receipts) - len(arrived)
        return presented

    # ---------- 分布视图 ----------

    def distribution(self, batch_id: int) -> tuple[dict[str, Any] | None, str]:
        """批次请求结果分布：统计按逻辑请求去重，可展开到每条请求的尝试明细。"""
        batch = store.find("request_batch", batch_id)
        if batch is None:
            return None, f"调用批次 {batch_id} 不存在或已归档"
        code = str(batch.get("批次编号", ""))
        requests = [self._present_request(req) for req in self.list_requests(code)]
        stats: dict[str, int] = {
            "逻辑请求数": len(requests),
            "成功": 0,
            "失败待补采": 0,
            "补采中": 0,
            "待回执": 0,
            "已跳过": 0,
            "未收齐": 0,
        }
        for item in requests:
            state = item["当前结果"]
            stats[state] = stats.get(state, 0) + 1
            if state in INCOMPLETE_STATES:
                stats["未收齐"] += 1
        # 参数相同的独立请求：提示它们仍分别计入统计
        param_groups: dict[str, list[str]] = {}
        for item in requests:
            param_groups.setdefault(str(item.get("请求参数", "")), []).append(str(item["请求编号"]))
        same_params = [codes for codes in param_groups.values() if len(codes) > 1]
        events = [event for req in requests for event in self.events_of(str(req["请求编号"]))]
        events.sort(key=lambda e: (str(e.get("时间", "")), int(e.get("id", 0))), reverse=True)
        payload = {
            "batch": batch,
            "stats": stats,
            "requests": requests,
            "incomplete": [item for item in requests if item["当前结果"] in INCOMPLETE_STATES],
            "same_params": same_params,
            "recent_events": events[:20],
            "观察时间": _now(),
        }
        return payload, "ok"

    def summary(self) -> list[dict[str, Any]]:
        """按批次列出尚未收齐的请求，供交接时先挑批次。"""
        items: list[dict[str, Any]] = []
        for batch in store.rows("request_batch"):
            code = str(batch.get("批次编号", ""))
            requests = [self._present_request(req) for req in self.list_requests(code)]
            if not requests:
                continue
            incomplete = [item for item in requests if item["当前结果"] in INCOMPLETE_STATES]
            items.append({
                "batch_id": batch.get("id"),
                "批次编号": code,
                "关联端点": batch.get("关联端点", ""),
                "批次状态": batch.get("status", ""),
                "逻辑请求数": len(requests),
                "成功": sum(1 for item in requests if item["当前结果"] == "成功"),
                "未收齐": len(incomplete),
                "未收齐请求": [str(item["请求编号"]) for item in incomplete],
            })
        return items

    def detail(self, request_id: int) -> tuple[dict[str, Any] | None, str]:
        """单条请求的尝试明细：全部回执（含在途）+ 交接变迁。"""
        req = self.find_request(request_id)
        if req is None:
            return None, f"采集请求 {request_id} 不存在"
        code = str(req["请求编号"])
        events = self.events_of(code)
        events.sort(key=lambda e: (str(e.get("时间", "")), int(e.get("id", 0))))
        payload = {
            "request": self._present_request(req),
            "receipts": self.receipts_of(code),
            "events": events,
        }
        return payload, "ok"

    # ---------- 回执同步（展开/刷新时拉取新到回执） ----------

    def sync_request(self, request_id: int) -> tuple[dict[str, Any] | None, str]:
        req = self.find_request(request_id)
        if req is None:
            return None, f"采集请求 {request_id} 不存在"
        change = self._arrive_receipts(req)
        payload = {
            "changes": [change] if change else [],
            "request": self._present_request(req),
        }
        return payload, "ok"

    def sync_batch(self, batch_id: int) -> tuple[dict[str, Any] | None, str]:
        batch = store.find("request_batch", batch_id)
        if batch is None:
            return None, f"调用批次 {batch_id} 不存在或已归档"
        changes = []
        for req in self.list_requests(str(batch.get("批次编号", ""))):
            change = self._arrive_receipts(req)
            if change:
                changes.append(change)
        return {"changes": changes}, "ok"

    def _arrive_receipts(self, req: dict[str, Any]) -> dict[str, Any] | None:
        """把该请求的在途回执落账；确认回执始终取尝试序号最大的已到达回执。"""
        code = str(req["请求编号"])
        inflight = [r for r in self.receipts_of(code) if r.get("到达状态") == "在途"]
        if not inflight:
            return None
        old_state = self.request_state(req)
        arrived_at = _now()
        for receipt in inflight:
            receipt["到达状态"] = "已到达"
            receipt["到达时间"] = arrived_at
        best = self.receipts_of(code, arrived_only=True)[-1]
        if str(req.get("确认回执", "")) == str(best["回执编号"]):
            # 新到回执早于当前确认回执（例如重放已成功，原批次回执才补到），只补登尝试记录
            self._log_event(
                req, old_state, old_state, str(best["回执编号"]),
                f"回执 {','.join(str(r['回执编号']) for r in inflight)} 补登到账，不改变已确认结果",
            )
            return None
        req["确认回执"] = best["回执编号"]
        new_state = self.request_state(req)
        self._log_event(
            req, old_state, new_state, str(best["回执编号"]),
            f"新到回执 {best['回执编号']}（{best['来源']}，结果{best['结果']}），交接状态更新",
        )
        return {
            "请求编号": code,
            "旧状态": old_state,
            "新状态": new_state,
            "新到回执": [str(r["回执编号"]) for r in inflight],
        }

    # ---------- 值班员处置：派发补采 / 跳过补采 ----------

    def dispatch(self, request_id: int) -> tuple[dict[str, Any] | None, str]:
        """从分布视图把单条请求派发到重放队列，并记录所用回执。"""
        req = self.find_request(request_id)
        if req is None:
            return None, f"采集请求 {request_id} 不存在"
        code = str(req["请求编号"])
        state = self.request_state(req)
        if state == "成功":
            return None, f"{code} 已凭回执 {req.get('确认回执', '')} 确认成功，无需补采"
        if state == "已跳过":
            return None, f"{code} 已跳过补采，不再派发"
        active = self.active_task_of(code)
        if active is not None:
            return None, f"{code} 已在重放队列中（{active.get('任务编号', '')}），无需重复派发"
        rows = store.rows("retry_queue")
        task_id = _next_id(rows)
        task = {
            "id": task_id,
            "任务编号": f"RETR-{task_id:04d}",
            "失败端点": req.get("关联端点", ""),
            "失败原因": f"交接补采：批次{req.get('批次编号', '')}请求{code}",
            "重试次数": 0,
            "最大重试": 3,
            "退避策略": "exponential:2s/baseline",
            "最后重试": "",
            "队列状态": "等待",
            "status": "待重试",
            "pending": True,
            "abnormal": False,
            "关联请求编号": code,
        }
        rows.append(task)
        req["处置方式"] = "补采"
        req["处置回执"] = req.get("确认回执", "")
        req["进入补采"] = True
        req["重放任务编号"] = task["任务编号"]
        basis = str(req["处置回执"]) or "无（尚无到达回执）"
        self._log_event(
            req, state, "补采中", str(req.get("确认回执", "")),
            f"值班员从交接分布视图派发补采，生成重放任务 {task['任务编号']}；依据回执：{basis}",
        )
        payload = {"task": task, "request": self._present_request(req)}
        return payload, f"已派发补采，重放任务 {task['任务编号']}（依据回执：{basis}）"

    def dispatch_batch(self, batch_id: int) -> tuple[dict[str, Any] | None, str]:
        """把该批尚未收齐的请求逐个派发补采。"""
        batch = store.find("request_batch", batch_id)
        if batch is None:
            return None, f"调用批次 {batch_id} 不存在或已归档"
        dispatched, skipped = [], []
        for req in self.list_requests(str(batch.get("批次编号", ""))):
            if self.request_state(req) not in ("待回执", "失败待补采"):
                continue
            payload, message = self.dispatch(int(req["id"]))
            if payload is not None:
                dispatched.append(str(req["请求编号"]))
            else:
                skipped.append(message)
        if not dispatched and not skipped:
            return {"dispatched": [], "skipped": []}, "该批没有待补采的请求"
        return {"dispatched": dispatched, "skipped": skipped}, \
            f"已派发 {len(dispatched)} 条补采" + (f"，跳过 {len(skipped)} 条" if skipped else "")

    def skip(self, request_id: int, remark: str | None = None) -> tuple[dict[str, Any] | None, str]:
        """值班员确认跳过补采，记录所依据的回执。"""
        req = self.find_request(request_id)
        if req is None:
            return None, f"采集请求 {request_id} 不存在"
        code = str(req["请求编号"])
        state = self.request_state(req)
        if state == "成功":
            return None, f"{code} 已确认成功，无需跳过"
        if state == "已跳过":
            return None, f"{code} 已是跳过状态"
        if state == "补采中":
            return None, f"{code} 已有重放任务在进行（{req.get('重放任务编号', '')}），请先处理任务"
        req["处置方式"] = "跳过"
        req["处置回执"] = req.get("确认回执", "")
        basis = str(req["处置回执"]) or "无（尚无到达回执）"
        note = remark or "值班员确认跳过补采"
        self._log_event(req, state, "已跳过", str(req.get("确认回执", "")), f"{note}；依据回执：{basis}")
        payload = {"request": self._present_request(req)}
        return payload, f"{code} 已跳过补采（依据回执：{basis}）"

    # ---------- 重放结果回写交接清单 ----------

    def sync_replay_outcome(self, task: dict[str, Any], success: bool) -> dict[str, Any] | None:
        """重放任务出结果后写一份重放回执，并把确认结果同步到交接清单。"""
        code = str(task.get("关联请求编号", ""))
        if not code:
            return None
        req = self.find_request_by_code(code)
        if req is None:
            return None
        rows = store.rows(RECEIPT_TABLE)
        receipt_id = _next_id(rows)
        receipt = {
            "id": receipt_id,
            "回执编号": f"RCPT-{receipt_id:04d}",
            "请求编号": code,
            "批次编号": req.get("批次编号", ""),
            "来源": "重放",
            "尝试序号": len(self.receipts_of(code)) + 1,
            "结果": "成功" if success else "失败",
            "错误信息": "" if success else "重放仍失败",
            "到达时间": _now(),
            "关联重放任务": task.get("任务编号", ""),
            "到达状态": "已到达",
        }
        rows.append(receipt)
        old_state = self.request_state(req)
        req["确认回执"] = receipt["回执编号"]
        new_state = self.request_state(req)
        self._log_event(
            req, old_state, new_state, str(receipt["回执编号"]),
            f"重放任务 {task.get('任务编号', '')} 回执{receipt['结果']}，结果同步到交接清单",
        )
        return receipt

    # ---------- 交接变迁 ----------

    def _log_event(self, req: dict[str, Any], old: str, new: str, receipt_code: str, note: str) -> None:
        rows = store.rows(EVENT_TABLE)
        rows.append({
            "id": _next_id(rows),
            "请求编号": req.get("请求编号", ""),
            "时间": _now(),
            "变化": f"{old}→{new}",
            "依据回执": receipt_code,
            "说明": note,
        })
