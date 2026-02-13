"""参数化验证 Demo — 模板 + inline 覆盖

YAML 模板 (local / remote) 提供基线参数，
测试用例只写差异部分:

    make_plan("local", branch="br_fix", cases=["tc1"])

运行:
  pytest demos/ -v
  pytest demos/ -k "timing" -v
  pytest demos/ -k "remote" -v
"""

from __future__ import annotations

import pytest

from framework.services.execution_orchestrator import ExecutionOrchestrator

# =========================================================================
# 用例 A: 本地 PC 验证
# =========================================================================


class TestLocalSmoke:
    """本地 PC + EDA 仿真 smoke 场景"""

    @pytest.mark.parametrize("branch,cases", [
        ("br_fix_timing_closure", ["sanity_check", "basic_func"]),
        ("br_fix_clock_gating",   ["sanity_check"]),
    ])
    def test_branch_smoke(self, mock_container, make_plan, branch, cases):
        plan = make_plan("local", branch=branch, cases=cases)
        report = ExecutionOrchestrator(container=mock_container).run(plan)

        assert report.success is True
        assert report.run_id != ""

    def test_default_smoke(self, mock_container, make_plan):
        """模板默认值即可跑通"""
        plan = make_plan("local")
        report = ExecutionOrchestrator(container=mock_container).run(plan)
        assert report.success is True


class TestLocalRegression:
    """本地 PC 全量回归"""

    @pytest.mark.parametrize("parallel", [4, 8, 16])
    def test_parallel_scaling(self, mock_container, make_plan, parallel):
        plan = make_plan("local",
                         branch="br_perf_optimization",
                         suite="regression",
                         parallel=parallel,
                         cases=[])  # 空 = 全部用例
        report = ExecutionOrchestrator(container=mock_container).run(plan)
        assert report.success is True

    @pytest.mark.parametrize("snapshot", ["20250206B003", "20250210B001"])
    def test_snapshot_versions(self, mock_container, make_plan, snapshot):
        plan = make_plan("local", snapshot_id=snapshot)
        assert plan.snapshot_id == snapshot


# =========================================================================
# 用例 B: 远程服务器执行
# =========================================================================


class TestRemote:
    """远程服务器 B 编排执行"""

    @pytest.mark.parametrize("branch,cases", [
        ("br_fix_timing_closure", ["sanity_check", "basic_func"]),
        ("br_dft_scan_chain",     ["scan_test_1", "scan_test_2"]),
    ])
    def test_remote_execute(self, mock_container, make_plan, branch, cases):
        plan = make_plan("remote", branch=branch, cases=cases)
        report = ExecutionOrchestrator(container=mock_container).run(plan)

        assert report.success is True
        mock_container.env.release.assert_called_once()

    def test_remote_regression(self, mock_container, make_plan):
        plan = make_plan("remote", suite="regression", parallel=8, cases=[])
        report = ExecutionOrchestrator(container=mock_container).run(plan)
        assert report.success is True


# =========================================================================
# 通用: 编排步骤 & Plan 属性
# =========================================================================


class TestSteps:
    """验证 7 步编排的完整性"""

    @pytest.mark.parametrize("tpl", ["local", "remote"])
    def test_all_steps_executed(self, mock_container, make_plan, tpl):
        plan = make_plan(tpl, branch="br_fix_timing_closure")
        report = ExecutionOrchestrator(container=mock_container).run(plan)

        steps = {s["step"] for s in report.steps}
        assert {"provision_env", "checkout", "build", "execute", "collect", "teardown"} <= steps

    @pytest.mark.parametrize("tpl", ["local", "remote"])
    def test_teardown_always_releases(self, mock_container, make_plan, tpl):
        plan = make_plan(tpl)
        ExecutionOrchestrator(container=mock_container).run(plan)
        mock_container.env.release.assert_called_once()


class TestPlanConversion:
    """Plan → RunRequest 转换"""

    @pytest.mark.parametrize("tpl,expected_env", [
        ("local",  "sim_eda"),
        ("remote", "sim_eda_remote"),
    ])
    def test_env_mapping(self, make_plan, tpl, expected_env):
        plan = make_plan(tpl)
        req = plan.to_run_request()
        assert req.environment == expected_env

    def test_branch_override_in_plan(self, make_plan):
        plan = make_plan("local", branch="br_new_feature")
        assert plan.repo_ref_overrides["rtl_core"] == "br_new_feature"
