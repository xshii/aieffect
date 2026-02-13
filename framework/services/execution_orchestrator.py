"""执行编排器 — 7 步流水线（Step 模式）

将测试执行拆解为清晰的 7 个阶段，每个阶段为独立的 Step 类:

  1. ProvisionEnvStep   — 装配执行环境（最优先）
  2. CheckoutStep       — 检出代码仓（在环境中）
  3. BuildStep          — 编译构建
  4. AcquireStimuliStep — 获取激励
  5. ExecuteStep        — 执行用例
  6. CollectResultsStep — 收集结果
  7. TeardownStep       — 清理回收

环境优先于代码仓：环境决定代码仓检出位置。
使用 ServiceContainer 统一依赖注入，避免跨服务裸构造。
teardown 通过 try/finally 保证执行。
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass, field
from typing import Any

from framework.core.models import (
    BuildResult,
    ExecutionContext,
    RepoWorkspace,
    StimulusArtifact,
    SuiteResult,
)
from framework.services.container import ServiceContainer
from framework.services.run_service import RunRequest

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationPlan:
    """编排计划 — 声明本次执行需要哪些资源"""

    suite: str = "default"
    config_path: str = "configs/default.yml"
    parallel: int = 1

    build_env_name: str = ""
    exe_env_name: str = ""
    environment: str = ""

    repo_names: list[str] = field(default_factory=list)
    repo_ref_overrides: dict[str, str] = field(default_factory=dict)
    build_names: list[str] = field(default_factory=list)
    stimulus_names: list[str] = field(default_factory=list)

    params: dict[str, str] = field(default_factory=dict)
    snapshot_id: str = ""
    case_names: list[str] = field(default_factory=list)

    def to_run_request(self) -> RunRequest:
        """转换为 RunRequest（消除手动字段拷贝）"""
        return RunRequest(
            suite=self.suite,
            config_path=self.config_path,
            parallel=self.parallel,
            environment=self.exe_env_name or self.environment,
            params=self.params or None,
            snapshot_id=self.snapshot_id,
            case_names=self.case_names or None,
        )


@dataclass
class OrchestrationReport:
    """编排执行报告"""

    plan: OrchestrationPlan
    context: ExecutionContext
    suite_result: SuiteResult | None = None
    run_id: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.suite_result is not None and self.suite_result.success


# =========================================================================
# Step 抽象基类
# =========================================================================


class OrchestratorStep(abc.ABC):
    """编排步骤基类 — 每个阶段实现 execute 方法"""

    name: str = ""

    def __init__(self, container: ServiceContainer) -> None:
        self.c = container

    @abc.abstractmethod
    def execute(
        self,
        plan: OrchestrationPlan,
        ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        """执行本步骤"""


# =========================================================================
# 各步骤实现
# =========================================================================


class ProvisionEnvStep(OrchestratorStep):
    """步骤1: 装配构建环境和执行环境"""

    name = "provision_env"

    def execute(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        build_env = plan.build_env_name
        exe_env = plan.exe_env_name or plan.environment
        if not build_env and not exe_env:
            report.steps.append({
                "step": self.name, "status": "skipped",
                "detail": "未指定环境",
            })
            return
        session = self.c.env.apply(
            build_env_name=build_env, exe_env_name=exe_env,
        )
        ctx.env_session = session
        report.steps.append({
            "step": self.name, "status": "done",
            "build_env": build_env, "exe_env": exe_env,
            "session_id": session.session_id,
            "variables_count": len(session.resolved_vars),
        })
        logger.info(
            "[Step 1] 环境装配完成: build=%s exe=%s (%d 变量)",
            build_env, exe_env, len(session.resolved_vars),
        )


class CheckoutStep(OrchestratorStep):
    """步骤2: 检出代码仓到本地工作空间"""

    name = "checkout"

    def execute(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        if not plan.repo_names:
            report.steps.append({"step": self.name, "status": "skipped"})
            return
        workspaces: list[RepoWorkspace] = []
        for repo_name in plan.repo_names:
            ref = plan.repo_ref_overrides.get(repo_name, "")
            ws = self.c.repo.checkout(repo_name, ref_override=ref)
            workspaces.append(ws)
        ctx.repos = workspaces
        statuses = {ws.spec.name: ws.status for ws in workspaces}
        report.steps.append({
            "step": self.name, "status": "done", "repos": statuses,
        })
        logger.info("[Step 2] 代码仓检出完成: %s", statuses)


class BuildStep(OrchestratorStep):
    """步骤3: 执行构建任务，生成可执行文件或库"""

    name = "build"

    def execute(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        if not plan.build_names:
            report.steps.append({"step": self.name, "status": "skipped"})
            return
        env_vars = (
            ctx.env_session.resolved_vars if ctx.env_session else None
        )
        results: list[BuildResult] = []
        for build_name in plan.build_names:
            ref = plan.repo_ref_overrides.get(build_name, "")
            result = self.c.build.build(build_name, env_vars=env_vars, repo_ref=ref)
            results.append(result)
        ctx.builds = results
        statuses = {r.spec.name: r.status for r in results}
        report.steps.append({
            "step": self.name, "status": "done", "builds": statuses,
        })
        logger.info("[Step 3] 构建完成: %s", statuses)


class AcquireStimuliStep(OrchestratorStep):
    """步骤4: 获取测试激励（输入数据/测试向量）"""

    name = "acquire_stimuli"

    def execute(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        if not plan.stimulus_names:
            report.steps.append({"step": self.name, "status": "skipped"})
            return
        artifacts: list[StimulusArtifact] = []
        for stim_name in plan.stimulus_names:
            art = self.c.stimulus.acquire(stim_name)
            artifacts.append(art)
        ctx.stimuli = artifacts
        statuses = {a.spec.name: a.status for a in artifacts}
        report.steps.append({
            "step": self.name, "status": "done", "stimuli": statuses,
        })
        logger.info("[Step 4] 激励获取完成: %s", statuses)


class ExecuteStep(OrchestratorStep):
    """步骤5: 执行测试用例集，收集执行结果"""

    name = "execute"

    def execute(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        req = plan.to_run_request()
        result = self.c.run.execute(req)
        report.suite_result = result
        report.steps.append({
            "step": self.name, "status": "done",
            "total": result.total, "passed": result.passed,
            "failed": result.failed, "errors": result.errors,
        })
        logger.info(
            "[Step 5] 执行完成: total=%d passed=%d failed=%d errors=%d",
            result.total, result.passed, result.failed, result.errors,
        )


class CollectResultsStep(OrchestratorStep):
    """步骤6: 收集并保存测试结果到历史记录"""

    name = "collect"

    def execute(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        if report.suite_result is None:
            report.steps.append({"step": self.name, "status": "skipped"})
            return
        env_name = plan.exe_env_name or plan.environment
        run_id = self.c.result.save(
            report.suite_result,
            suite=plan.suite,
            environment=env_name,
            snapshot_id=plan.snapshot_id,
            params=plan.params,
            build_env=plan.build_env_name,
            exe_env=env_name,
        )
        report.run_id = run_id
        report.steps.append({
            "step": self.name, "status": "done", "run_id": run_id,
        })
        logger.info("[Step 6] 结果已收集: run_id=%s", run_id)


class TeardownStep(OrchestratorStep):
    """步骤7: 清理环境资源，释放会话"""

    name = "teardown"

    def execute(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        if ctx.env_session and ctx.env_session.status == "applied":
            self.c.env.release(ctx.env_session)
        report.steps.append({"step": self.name, "status": "done"})
        logger.info("[Step 7] 清理完成")


# =========================================================================
# 编排器
# =========================================================================


class ExecutionOrchestrator:
    """7 步执行编排器（Step 组合，try/finally 保证 teardown）"""

    def __init__(self, container: ServiceContainer | None = None) -> None:
        self.c = container or ServiceContainer()
        self.pipeline: list[OrchestratorStep] = [
            ProvisionEnvStep(self.c),
            CheckoutStep(self.c),
            BuildStep(self.c),
            AcquireStimuliStep(self.c),
            ExecuteStep(self.c),
            CollectResultsStep(self.c),
        ]
        self._teardown = TeardownStep(self.c)

    def run(self, plan: OrchestrationPlan) -> OrchestrationReport:
        ctx = ExecutionContext(params=plan.params)
        report = OrchestrationReport(plan=plan, context=ctx)

        try:
            for step in self.pipeline:
                step.execute(plan, ctx, report)
        finally:
            self._teardown.execute(plan, ctx, report)

        return report
