"""ExecutionOrchestrator 单元测试"""

from __future__ import annotations

from framework.services.execution_orchestrator import OrchestrationPlan, OrchestrationReport


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

    def test_plan_with_all_fields(self):
        plan = OrchestrationPlan(
            suite="regression",
            parallel=4,
            repo_names=["rtl", "tb"],
            repo_ref_overrides={"rtl": "v2.0"},
            environment="sim_env",
            build_names=["compile"],
            stimulus_names=["rand_vectors"],
            params={"seed": "42"},
            snapshot_id="snap-001",
            case_names=["test_a", "test_b"],
        )
        assert plan.suite == "regression"
        assert len(plan.repo_names) == 2
        assert plan.repo_ref_overrides["rtl"] == "v2.0"


class TestOrchestrationReport:
    """编排报告测试"""

    def test_empty_report_not_success(self):
        plan = OrchestrationPlan()
        from framework.core.models import ExecutionContext
        report = OrchestrationReport(plan=plan, context=ExecutionContext())
        assert report.success is False
        assert report.run_id == ""
        assert report.steps == []
