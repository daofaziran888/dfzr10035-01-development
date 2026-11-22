"""重放队列领域服务：管理失败请求重试，与 request_batch、call_log、api_monitor 联动。"""
from __future__ import annotations

from datetime import datetime

from app.services.base import BaseModuleService
from app.services.batch_handover import ACTIVE_TASK_STATUS, BatchHandoverService
from app.store import store


class RetryQueueService(BaseModuleService):
    MODULE = "retry_queue"
    ENTITY = "重放任务"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["任务编号", "失败端点", "失败原因", "重试次数", "最大重试", "退避策略", "最后重试", "队列状态"]
    REQUIRED_FIELDS = ["任务编号", "失败端点", "失败原因"]
    STATUS_ORDER = ["待重试", "重试中", "已成功", "永久失败"]
    ACTION_RULES = {"加入队列": "重试中", "手动重试": "已成功", "标记失败": "永久失败"}
    NEGATIVE_ACTIONS = []

    def run_action(self, entry_id: int, action: str):
        """重试中/已成功时联动写调用日志和更新监控；永久失败时触发告警。

        关联了交接请求的任务，取单前先问交接清单：已确认成功或已跳过的本轮不再取单。
        """
        if action in ("加入队列", "手动重试"):
            task = store.find(self.MODULE, entry_id)
            if task is not None:
                block = self._handover_block_reason(task)
                if block:
                    return None, block
        entry, message = super().run_action(entry_id, action)
        if entry is None:
            return entry, message
        handover = BatchHandoverService()
        if action == "加入队列":
            self._log_retry_start(entry)
        elif action == "手动重试":
            self._log_retry_success(entry)
            receipt = handover.sync_replay_outcome(entry, success=True)
            self._update_monitor_health(entry)
            message += "，已更新调用日志和监控健康上报"
            if receipt is not None:
                message += f"，重放回执 {receipt['回执编号']} 已同步到交接清单"
        elif action == "标记失败":
            receipt = handover.sync_replay_outcome(entry, success=False)
            self._trigger_alert(entry)
            message += "，已触发监控告警"
            if receipt is not None:
                message += f"，重放回执 {receipt['回执编号']} 已同步到交接清单"
        return entry, message

    def _handover_block_reason(self, task: dict) -> str | None:
        """交接清单已确认的请求，本轮取单直接拦下并说明依据回执。"""
        code = str(task.get("关联请求编号", ""))
        if not code:
            return None
        handover = BatchHandoverService()
        req = handover.find_request_by_code(code)
        if req is None:
            return None
        state = handover.request_state(req)
        if state == "成功":
            return (f"交接清单已凭回执 {req.get('确认回执', '')} 确认 {code} 成功，"
                    f"任务 {task.get('任务编号', '')} 本轮不再取单")
        if state == "已跳过":
            return f"交接清单已标记 {code} 跳过补采，任务 {task.get('任务编号', '')} 本轮不再取单"
        return None

    def current_round(self) -> dict:
        """本轮取单视图：可取单、被交接结果跳过、以及已确认请求清单。

        补采中断后续做时，已确认的请求在这里依然查得见（含确认所用回执）。
        """
        handover = BatchHandoverService()
        take, skip = [], []
        for task in store.rows(self.MODULE):
            if task.get("status") not in ACTIVE_TASK_STATUS:
                continue
            code = str(task.get("关联请求编号", ""))
            req = handover.find_request_by_code(code) if code else None
            base = {
                "任务编号": task.get("任务编号", ""),
                "失败端点": task.get("失败端点", ""),
                "队列状态": task.get("队列状态", ""),
                "关联请求编号": code or "—",
            }
            if req is None:
                take.append({**base, "交接状态": "无交接关联"})
                continue
            state = handover.request_state(req)
            if state == "成功":
                skip.append({
                    **base,
                    "交接状态": state,
                    "依据回执": req.get("确认回执", ""),
                    "原因": f"交接已凭回执 {req.get('确认回执', '')} 确认成功，本轮不再取单",
                })
            elif state == "已跳过":
                skip.append({
                    **base,
                    "交接状态": state,
                    "依据回执": req.get("处置回执", ""),
                    "原因": "值班员已标记跳过补采",
                })
            else:
                take.append({**base, "交接状态": state})
        confirmed = [
            {
                "请求编号": req.get("请求编号", ""),
                "批次编号": req.get("批次编号", ""),
                "当前结果": handover.request_state(req),
                "确认回执": req.get("确认回执", "") or req.get("处置回执", ""),
            }
            for req in handover.list_requests()
            if handover.request_state(req) in ("成功", "已跳过")
        ]
        return {
            "取单时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "本轮可取": take,
            "本轮跳过": skip,
            "已确认请求": confirmed,
        }

    def _log_retry_start(self, task: dict):
        log_rows = store.rows("call_log")
        tid = str(task["id"]).zfill(4)
        log_rows.append({
            "id": max((int(r.get("id", 0)) for r in log_rows), default=0) + 1,
            "记录编号": f"CALL-RETRY-{tid}",
            "接口端点": task.get("失败端点", ""),
            "请求参数": f"retry:task={tid}",
            "响应状态": "retrying",
            "响应耗时(ms)": 0,
            "返回行数": 0,
            "错误信息": task.get("失败原因", ""),
            "调用时间": "2026-11-17",
            "status": "超时", "pending": True, "abnormal": True,
        })

    def _log_retry_success(self, task: dict):
        tid = str(task["id"]).zfill(4)
        for log in store.rows("call_log"):
            if log.get("记录编号") == f"CALL-RETRY-{tid}":
                log["status"] = "成功"
                log["响应状态"] = "200"
                log["响应耗时(ms)"] = 150
                log["返回行数"] = 1
                break

    def _update_monitor_health(self, task: dict):
        """重试成功后联动刷新监控健康度。"""
        endpoint = task.get("失败端点", "")
        for mon in store.rows("api_monitor"):
            if mon.get("目标端点") == endpoint:
                mon["最近采样"] = "2026-11-17"
                if mon.get("status") == "已告警":
                    mon["status"] = "监控中"
                    mon["pending"] = True

    def _trigger_alert(self, task: dict):
        """永久失败触发监控告警和治理报告。"""
        endpoint = task.get("失败端点", "")
        tid = str(task["id"]).zfill(4)
        # 更新监控状态
        for mon in store.rows("api_monitor"):
            if mon.get("目标端点") == endpoint:
                mon["status"] = "已告警"
                mon["pending"] = False
                mon["最近采样"] = "2026-11-17"
        # 创建治理报告条目
        gov_rows = store.rows("govern_report")
        gov_rows.append({
            "id": max((int(r.get("id", 0)) for r in gov_rows), default=0) + 1,
            "报告编号": f"GOVE-RETRY-{tid}",
            "评估范围": f"重放队列永久失败: {endpoint}",
            "合规指标": "数据采集完整性",
            "当前得分": 60.0,
            "改进事项": f"任务{tid}重试耗尽，需人工介入",
            "评估周期": "2026-Q4",
            "负责人": "运维值班",
            "生成时间": "2026-11-17",
            "status": "待生成", "pending": True, "abnormal": True,
        })

    def calc_recovery_rate(self) -> dict:
        """跨模块恢复率统计：分析重放队列成功/失败分布及关联调用日志。"""
        retries = store.rows("retry_queue")
        total = len(retries)
        success = sum(1 for r in retries if r.get("status") == "已成功")
        perm_fail = sum(1 for r in retries if r.get("status") == "永久失败")
        # 关联调用日志
        logs_related = [
            l for l in store.rows("call_log")
            if "retry" in str(l.get("请求参数", ""))
        ]
        return {
            "total_retries": total,
            "success": success,
            "permanent_fail": perm_fail,
            "recovery_rate": success / total if total else 0.0,
            "logged_events": len(logs_related),
        }