"""执行编排器 - 协调 7 步流水线

职责：
- 协调 7 个步骤的执行顺序
- 保证 teardown 在 finally 中执行
- 构建执行上下文和报告
"""

from __future__ import annotations

from framework.core.models import ExecutionContext
from framework.services.container import ServiceContainer
from framework.services.orchestrator.models import OrchestrationPlan, OrchestrationReport
from framework.services.orchestrator.steps import OrchestrationSteps


class Orchestrator:
    """7 步执行编排器（环境优先，try/finally 保证 teardown）"""

    def __init__(self, container: ServiceContainer | None = None) -> None:
        self.c = container or ServiceContainer()
        self.steps = OrchestrationSteps(self.c)

    def run(self, plan: OrchestrationPlan) -> OrchestrationReport:
        """执行编排流程"""
        ctx = ExecutionContext(params=plan.params)
        report = OrchestrationReport(plan=plan, context=ctx)

        try:
            self.steps.provision_env(plan, ctx, report)
            self.steps.checkout(plan, ctx, report)
            self.steps.build(plan, ctx, report)
            self.steps.acquire_stimuli(plan, ctx, report)
            self.steps.execute(plan, report)
            self.steps.collect(plan, report)
        finally:
            self.steps.teardown(ctx, report)

        return report
