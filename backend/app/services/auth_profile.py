"""鉴权编排领域服务：管理API鉴权方案，与端点定义、限流策略联动。"""
from __future__ import annotations

from app.services.base import BaseModuleService
from app.store import store


class AuthProfileService(BaseModuleService):
    MODULE = "auth_profile"
    ENTITY = "鉴权方案"
    OPERATION_TERM = "校验"
    LIST_FIELDS = ["方案编号", "提供方", "鉴权类型", "密钥版本", "Token过期", "刷新策略", "轮换周期", "最近轮换"]
    REQUIRED_FIELDS = ["方案编号", "提供方", "鉴权类型"]
    STATUS_ORDER = ["草稿", "已生效", "即将过期", "已失效"]
    ACTION_RULES = {"启效方案": "已生效", "触发轮换": "即将过期", "标记失效": "已失效"}
    NEGATIVE_ACTIONS = []

    def check_auth_chain(self, provider_name: str) -> dict:
        """跨模块鉴权链路检查：读取提供方→鉴权方案→端点定义→限流策略的完整链路。"""
        # 1) 从提供方读取
        providers = [
            p for p in store.rows("api_provider")
            if p.get("提供方名称") == provider_name
        ]
        if not providers:
            return {"ok": False, "message": f"提供方 {provider_name} 未注册"}

        # 2) 从端点定义读取
        endpoints = [
            e for e in store.rows("endpoint_def")
            if e.get("提供方") == provider_name
        ]

        # 3) 从限流策略读取
        rate_limits = []
        for ep in endpoints:
            ep_id = ep.get("端点编号", "")
            rate_limits.extend([
                r for r in store.rows("rate_limit")
                if r.get("目标端点") == ep_id
            ])

        return {
            "provider": provider_name,
            "auth_profiles": [a.get("方案编号") for a in store.rows("auth_profile")
                              if a.get("提供方") == provider_name],
            "endpoints": len(endpoints),
            "rate_limits": len(rate_limits),
            "chain_complete": len(endpoints) > 0 and len(rate_limits) > 0,
        }