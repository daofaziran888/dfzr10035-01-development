"""业务路由汇总：所有模块共用一套资源路由，由领域服务完成分派。"""
from __future__ import annotations

from app.routers import handover, resource

# 交接分布视图是固定路径，注册在通用资源路由 /api/{module} 之前
ROUTERS = [handover, resource]
