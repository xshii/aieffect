"""执行编排器 — 7 步流水线

将测试执行拆解为清晰的 7 个阶段:

  1. provision_env     — 装配执行环境（最优先）
  2. checkout_repos    — 检出代码仓（在环境中）
  3. build             — 编译构建
  4. acquire_stimuli   — 获取激励
  5. execute           — 执行用例
  6. collect_results   — 收集结果
  7. teardown          — 清理回收

环境优先于代码仓：环境决定代码仓检出位置。
使用 ServiceContainer 统一依赖注入，避免跨服务裸构造。
teardown 通过 try/finally 保证执行。
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


class ExecutionOrchestrator:
    """7 步执行编排器（环境优先，try/finally 保证 teardown）"""

    def __init__(self, container: ServiceContainer | None = None) -> None:
        self.c = container or ServiceContainer()

    def run(self, plan: OrchestrationPlan) -> OrchestrationReport:
        ctx = ExecutionContext(params=plan.params)
        report = OrchestrationReport(plan=plan, context=ctx)

        try:
            self._step_provision_env(plan, ctx, report)
            self._step_checkout(plan, ctx, report)
            self._step_build(plan, ctx, report)
            self._step_acquire_stimuli(plan, ctx, report)
            self._step_execute(plan, report)
            self._step_collect(plan, report)
        finally:
            self._step_teardown(ctx, report)

        return report

    # ---- 各阶段实现 ----

    def _step_provision_env(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        build_env = plan.build_env_name
        exe_env = plan.exe_env_name or plan.environment
        if not build_env and not exe_env:
            report.steps.append({
                "step": "provision_env", "status": "skipped",
                "detail": "未指定环境",
            })
            return
        session = self.c.env.apply(
            build_env_name=build_env, exe_env_name=exe_env,
        )
        ctx.env_session = session
        report.steps.append({
            "step": "provision_env", "status": "done",
            "build_env": build_env, "exe_env": exe_env,
            "session_id": session.session_id,
            "variables_count": len(session.resolved_vars),
        })
        logger.info(
            "[Step 1] 环境装配完成: build=%s exe=%s (%d 变量)",
            build_env, exe_env, len(session.resolved_vars),
        )

    def _step_checkout(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        if not plan.repo_names:
            report.steps.append({
                "step": "checkout", "status": "skipped",
            })
            return
        workspaces: list[RepoWorkspace] = []
        for name in plan.repo_names:
            ref = plan.repo_ref_overrides.get(name, "")
            ws = self.c.repo.checkout(name, ref_override=ref)
            workspaces.append(ws)
        ctx.repos = workspaces
        statuses = {ws.spec.name: ws.status for ws in workspaces}
        report.steps.append({
            "step": "checkout", "status": "done", "repos": statuses,
        })
        logger.info("[Step 2] 代码仓检出完成: %s", statuses)

    def _step_build(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        if not plan.build_names:
            report.steps.append({
                "step": "build", "status": "skipped",
            })
            return
        env_vars = (
            ctx.env_session.resolved_vars if ctx.env_session else None
        )
        results: list[BuildResult] = []
        for name in plan.build_names:
            ref = plan.repo_ref_overrides.get(name, "")
            result = self.c.build.build(name, env_vars=env_vars, repo_ref=ref)
            results.append(result)
        ctx.builds = results
        statuses = {r.spec.name: r.status for r in results}
        report.steps.append({
            "step": "build", "status": "done", "builds": statuses,
        })
        logger.info("[Step 3] 构建完成: %s", statuses)

    def _step_acquire_stimuli(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        if not plan.stimulus_names:
            report.steps.append({
                "step": "acquire_stimuli", "status": "skipped",
            })
            return
        artifacts: list[StimulusArtifact] = []
        for name in plan.stimulus_names:
            art = self.c.stimulus.acquire(name)
            artifacts.append(art)
        ctx.stimuli = artifacts
        statuses = {a.spec.name: a.status for a in artifacts}
        report.steps.append({
            "step": "acquire_stimuli", "status": "done",
            "stimuli": statuses,
        })
        logger.info("[Step 4] 激励获取完成: %s", statuses)

    def _step_execute(
        self, plan: OrchestrationPlan,
        report: OrchestrationReport,
    ) -> None:
        req = plan.to_run_request()
        result = self.c.run.execute(req)
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
        self, plan: OrchestrationPlan,
        report: OrchestrationReport,
    ) -> None:
        if report.suite_result is None:
            report.steps.append({
                "step": "collect", "status": "skipped",
            })
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
            "step": "collect", "status": "done", "run_id": run_id,
        })
        logger.info("[Step 6] 结果已收集: run_id=%s", run_id)

    def _step_teardown(
        self, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        if ctx.env_session and ctx.env_session.status == "applied":
            self.c.env.release(ctx.env_session)
        report.steps.append({"step": "teardown", "status": "done"})
        logger.info("[Step 7] 清理完成")
