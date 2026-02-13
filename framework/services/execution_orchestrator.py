"""执行编排器 - 门面类（向后兼容）

职责：
- 保持向后兼容性
- 代理到新的模块化实现

重构说明：
- 原 258 行单体类拆分为 3 个模块
- models: 数据模型
- steps: 步骤实现
- orchestrator: 协调器
"""

from __future__ import annotations

from framework.services.container import ServiceContainer

# 导出数据模型（保持向后兼容）
from framework.services.orchestrator.models import (
    OrchestrationPlan,
    OrchestrationReport,
)

# 导入协调器
from framework.services.orchestrator.orchestrator import Orchestrator

__all__ = [
    "OrchestrationPlan",
    "OrchestrationReport",
    "ExecutionOrchestrator",
]


class ExecutionOrchestrator:
    """7 步执行编排器（向后兼容门面类）"""

    def __init__(self, container: ServiceContainer | None = None) -> None:
        self._orchestrator = Orchestrator(container)

    def run(self, plan: OrchestrationPlan) -> OrchestrationReport:
        """执行编排流程"""
        return self._orchestrator.run(plan)
