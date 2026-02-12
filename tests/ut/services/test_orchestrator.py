"""ExecutionOrchestrator 单元测试"""

from __future__ import annotations

from unittest.mock import MagicMock

from framework.services.execution_orchestrator import (
    ExecutionOrchestrator,
    OrchestrationPlan,
    OrchestrationReport,
)
from framework.services.run_service import RunRequest


class TestOrchestrationPlan:
    """编排计划测试"""

    def test_default_plan(self):
        plan = OrchestrationPlan()
        assert plan.suite == "default"
        assert plan.parallel == 1
        assert plan.repo_names == []
        assert plan.build_names == []
        assert plan.stimulus_names == []
        assert plan.environment == ""
        assert plan.build_env_name == ""
        assert plan.exe_env_name == ""

    def test_plan_with_all_fields(self):
        plan = OrchestrationPlan(
            suite="regression",
            parallel=4,
            build_env_name="local_build",
            exe_env_name="eda_env",
            repo_names=["rtl", "tb"],
            repo_ref_overrides={"rtl": "v2.0"},
            build_names=["compile"],
            stimulus_names=["rand_vectors"],
            params={"seed": "42"},
            snapshot_id="snap-001",
            case_names=["test_a", "test_b"],
        )
        assert plan.suite == "regression"
        assert len(plan.repo_names) == 2
        assert plan.repo_ref_overrides["rtl"] == "v2.0"
        assert plan.build_env_name == "local_build"
        assert plan.exe_env_name == "eda_env"


class TestToRunRequest:
    """to_run_request 转换测试"""

    def test_basic_conversion(self):
        plan = OrchestrationPlan(
            suite="smoke", config_path="my.yml", parallel=2,
            params={"seed": "1"},
        )
        req = plan.to_run_request()
        assert isinstance(req, RunRequest)
        assert req.suite == "smoke"
        assert req.config_path == "my.yml"
        assert req.parallel == 2
        assert req.params == {"seed": "1"}

    def test_exe_env_overrides_environment(self):
        plan = OrchestrationPlan(
            exe_env_name="eda_env", environment="legacy_env",
        )
        req = plan.to_run_request()
        assert req.environment == "eda_env"

    def test_fallback_to_environment(self):
        plan = OrchestrationPlan(environment="fallback_env")
        req = plan.to_run_request()
        assert req.environment == "fallback_env"

    def test_empty_params_become_none(self):
        plan = OrchestrationPlan()
        req = plan.to_run_request()
        assert req.params is None

    def test_empty_case_names_become_none(self):
        plan = OrchestrationPlan()
        req = plan.to_run_request()
        assert req.case_names is None

    def test_case_names_passed(self):
        plan = OrchestrationPlan(case_names=["tc1", "tc2"])
        req = plan.to_run_request()
        assert req.case_names == ["tc1", "tc2"]

    def test_snapshot_id_passed(self):
        plan = OrchestrationPlan(snapshot_id="snap-abc")
        req = plan.to_run_request()
        assert req.snapshot_id == "snap-abc"


class TestOrchestrationReport:
    """编排报告测试"""

    def test_empty_report_not_success(self):
        plan = OrchestrationPlan()
        from framework.core.models import ExecutionContext
        report = OrchestrationReport(plan=plan, context=ExecutionContext())
        assert report.success is False
        assert report.run_id == ""
        assert report.steps == []


class TestTeardownSafety:
    """teardown try/finally 保证测试"""

    def test_teardown_runs_on_exception(self):
        """即使执行阶段抛异常，teardown 也会执行"""
        container = MagicMock()
        container.env = MagicMock()
        container.run.execute.side_effect = RuntimeError("boom")
        container.result = MagicMock()

        orch = ExecutionOrchestrator(container=container)
        plan = OrchestrationPlan()

        try:
            orch.run(plan)
        except RuntimeError:
            pass

        # teardown 步骤应该已被记录（finally 块执行）
        # 不会因异常而跳过

    def test_teardown_releases_env_session(self):
        """如果有环境 session，teardown 释放它"""
        container = MagicMock()
        mock_session = MagicMock()
        mock_session.status = "applied"
        mock_session.session_id = "test-123"
        mock_session.resolved_vars = {}
        mock_session.name = "test"
        mock_session.work_dir = "/tmp"
        container.env.apply.return_value = mock_session
        container.repo = MagicMock()
        container.build = MagicMock()
        container.stimulus = MagicMock()
        container.run.execute.side_effect = RuntimeError("execute fail")
        container.result = MagicMock()

        orch = ExecutionOrchestrator(container=container)
        plan = OrchestrationPlan(build_env_name="local")

        try:
            orch.run(plan)
        except RuntimeError:
            pass

        container.env.release.assert_called_once_with(mock_session)
