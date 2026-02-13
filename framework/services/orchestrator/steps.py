"""编排器步骤实现 - 7 步流水线

步骤顺序：
1. provision_env - 装配执行环境
2. checkout - 检出代码仓
3. build - 编译构建
4. acquire_stimuli - 获取激励
5. execute - 执行用例
6. collect - 收集结果
7. teardown - 清理回收
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.services.container import ServiceContainer
    from framework.services.orchestrator.models import (
        OrchestrationPlan,
        OrchestrationReport,
    )

from framework.core.models import (
    BuildResult,
    ExecutionContext,
    RepoWorkspace,
    StimulusArtifact,
)

logger = logging.getLogger(__name__)


class OrchestrationSteps:
    """编排步骤集合"""

    def __init__(self, container: ServiceContainer) -> None:
        self.c = container

    def provision_env(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        """步骤1: 装配构建环境和执行环境"""
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

    def checkout(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        """步骤2: 检出代码仓到本地工作空间"""
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

    def build(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        """步骤3: 执行构建任务，生成可执行文件或库"""
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

    def acquire_stimuli(
        self, plan: OrchestrationPlan, ctx: ExecutionContext,
        report: OrchestrationReport,
    ) -> None:
        """步骤4: 获取测试激励（输入数据/测试向量）"""
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

    def execute(
        self, plan: OrchestrationPlan,
        report: OrchestrationReport,
    ) -> None:
        """步骤5: 执行测试用例集，收集执行结果"""
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

    def collect(
        self, plan: OrchestrationPlan,
        report: OrchestrationReport,
    ) -> None:
        """步骤6: 收集并保存测试结果到历史记录"""
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

    def teardown(
        self, ctx: ExecutionContext, report: OrchestrationReport,
    ) -> None:
        """步骤7: 清理环境资源，释放会话"""
        if ctx.env_session and ctx.env_session.status == "applied":
            self.c.env.release(ctx.env_session)
        report.steps.append({"step": "teardown", "status": "done"})
        logger.info("[Step 7] 清理完成")
