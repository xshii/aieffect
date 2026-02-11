"""执行编排器 — 7 步流水线

将测试执行拆解为清晰的 7 个阶段:

  1. checkout_repos    — 检出代码仓
  2. provision_env     — 装配执行环境
  3. build             — 编译构建
  4. acquire_stimuli   — 获取激励
  5. execute           — 执行用例
  6. collect_results   — 收集结果
  7. teardown          — 清理回收

每个阶段由对应的 Service 驱动，Orchestrator 只负责编排。
"""

from __future__ import annotations

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
from framework.services.run_service import RunRequest, RunService

logger = logging.getLogger(__name__)


@dataclass
class OrchestrationPlan:
    """编排计划 — 声明本次执行需要哪些资源"""

    suite: str = "default"
    config_path: str = "configs/default.yml"
    parallel: int = 1

    # 可选：要检出的代码仓
    repo_names: list[str] = field(default_factory=list)
    repo_ref_overrides: dict[str, str] = field(default_factory=dict)

    # 可选：要装配的环境
    environment: str = ""

    # 可选：要执行的构建
    build_names: list[str] = field(default_factory=list)

    # 可选：要获取的激励
    stimulus_names: list[str] = field(default_factory=list)

    # 运行时参数
    params: dict[str, str] = field(default_factory=dict)
    snapshot_id: str = ""
    case_names: list[str] = field(default_factory=list)


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


class ExecutionOrchestrator:
    """7 步执行编排器"""

    def run(self, plan: OrchestrationPlan) -> OrchestrationReport:
        """按 7 步流水线执行"""
        ctx = ExecutionContext(params=plan.params)
        report = OrchestrationReport(plan=plan, context=ctx)

        # Step 1: 检出代码仓
        self._step_checkout(plan, ctx, report)

        # Step 2: 装配环境
        self._step_provision_env(plan, ctx, report)

        # Step 3: 构建
        self._step_build(plan, ctx, report)

        # Step 4: 获取激励
        self._step_acquire_stimuli(plan, ctx, report)

        # Step 5: 执行用例
        self._step_execute(plan, ctx, report)

        # Step 6: 收集结果
        self._step_collect(plan, ctx, report)

        # Step 7: 清理回收
        self._step_teardown(ctx, report)

        return report

    # ---- 各阶段实现 ----

    def _step_checkout(
        self, plan: OrchestrationPlan, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        if not plan.repo_names:
            report.steps.append({"step": "checkout", "status": "skipped", "detail": "无代码仓"})
            return
        from framework.services.repo_service import RepoService
        svc = RepoService()
        workspaces: list[RepoWorkspace] = []
        for name in plan.repo_names:
            ref = plan.repo_ref_overrides.get(name, "")
            ws = svc.checkout(name, ref_override=ref)
            workspaces.append(ws)
        ctx.repos = workspaces
        statuses = {ws.spec.name: ws.status for ws in workspaces}
        report.steps.append({"step": "checkout", "status": "done", "repos": statuses})
        logger.info("[Step 1] 代码仓检出完成: %s", statuses)

    def _step_provision_env(
        self, plan: OrchestrationPlan, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        if not plan.environment:
            report.steps.append({"step": "provision_env", "status": "skipped", "detail": "未指定环境"})
            return
        from framework.services.env_service import EnvService
        svc = EnvService()
        session = svc.provision(plan.environment)
        ctx.env_session = session
        report.steps.append({
            "step": "provision_env", "status": "done",
            "environment": plan.environment,
            "variables_count": len(session.resolved_vars),
        })
        logger.info("[Step 2] 环境装配完成: %s (%d 变量)", plan.environment, len(session.resolved_vars))

    def _step_build(
        self, plan: OrchestrationPlan, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        if not plan.build_names:
            report.steps.append({"step": "build", "status": "skipped", "detail": "无构建任务"})
            return
        from framework.services.build_service import BuildService
        svc = BuildService()
        env_vars = ctx.env_session.resolved_vars if ctx.env_session else None
        results: list[BuildResult] = []
        for name in plan.build_names:
            result = svc.build(name, env_vars=env_vars)
            results.append(result)
        ctx.builds = results
        statuses = {r.spec.name: r.status for r in results}
        report.steps.append({"step": "build", "status": "done", "builds": statuses})
        logger.info("[Step 3] 构建完成: %s", statuses)

    def _step_acquire_stimuli(
        self, plan: OrchestrationPlan, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        if not plan.stimulus_names:
            report.steps.append({"step": "acquire_stimuli", "status": "skipped", "detail": "无激励需求"})
            return
        from framework.services.stimulus_service import StimulusService
        svc = StimulusService()
        artifacts: list[StimulusArtifact] = []
        for name in plan.stimulus_names:
            art = svc.acquire(name)
            artifacts.append(art)
        ctx.stimuli = artifacts
        statuses = {a.spec.name: a.status for a in artifacts}
        report.steps.append({"step": "acquire_stimuli", "status": "done", "stimuli": statuses})
        logger.info("[Step 4] 激励获取完成: %s", statuses)

    def _step_execute(
        self, plan: OrchestrationPlan, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        """执行用例 — 复用 RunService"""
        svc = RunService()
        req = RunRequest(
            suite=plan.suite,
            config_path=plan.config_path,
            parallel=plan.parallel,
            environment=plan.environment,
            params=plan.params or None,
            snapshot_id=plan.snapshot_id,
            case_names=plan.case_names or None,
        )
        result = svc.execute(req)
        report.suite_result = result
        report.steps.append({
            "step": "execute", "status": "done",
            "total": result.total, "passed": result.passed,
            "failed": result.failed, "errors": result.errors,
        })
        logger.info(
            "[Step 5] 执行完成: total=%d passed=%d failed=%d errors=%d",
            result.total, result.passed, result.failed, result.errors,
        )

    def _step_collect(
        self, plan: OrchestrationPlan, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        """收集并持久化结果"""
        if report.suite_result is None:
            report.steps.append({"step": "collect", "status": "skipped", "detail": "无执行结果"})
            return
        from framework.services.result_service import ResultService
        svc = ResultService()
        run_id = svc.save(
            report.suite_result,
            suite=plan.suite,
            environment=plan.environment,
            snapshot_id=plan.snapshot_id,
            params=plan.params,
        )
        report.run_id = run_id
        report.steps.append({"step": "collect", "status": "done", "run_id": run_id})
        logger.info("[Step 6] 结果已收集: run_id=%s", run_id)

    def _step_teardown(
        self, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        """清理环境会话"""
        if ctx.env_session and ctx.env_session.status == "ready":
            from framework.services.env_service import EnvService
            svc = EnvService()
            svc.teardown(ctx.env_session)
        report.steps.append({"step": "teardown", "status": "done"})
        logger.info("[Step 7] 清理完成")
