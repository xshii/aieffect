"""参数化验证 Demo — 模板 + inline 覆盖

YAML 模板 (local / remote) 提供基线参数，
测试用例只写差异部分:

    make_plan("local", branch="br_fix", cases=["tc1"])

运行:
  pytest demos/ -v                       # 全部 18 个参数化用例
  pytest demos/ -k "timing" -v           # 只跑含 timing 的场景
  pytest demos/ -k "remote" -v           # 只跑远程场景 (用例 B)
  pytest demos/ -k "regression" -v       # 只跑回归场景
  pytest demos/ -k "TestSteps" -v        # 只跑 7 步完整性验证

新增场景只需:
  1. 在 @pytest.mark.parametrize 中加一行参数元组
  2. 或新建一个 test_ 方法，调用 make_plan("local", ...) 即可
  不需要修改 YAML 或 conftest.py
"""

from __future__ import annotations

import pytest

from framework.services.execution_orchestrator import ExecutionOrchestrator

# =========================================================================
# 用例 A: 本地 PC 验证
#
# 场景: 开发者在本地 PC 上快速验证修复分支
# 模板: "local" — 本地构建 + 本地 EDA 仿真
# =========================================================================


class TestLocalSmoke:
    """本地 PC + EDA 仿真 smoke 场景

    验证目标: 不同修复分支的 smoke 用例能在本地环境跑通
    """

    @pytest.mark.parametrize("branch,cases", [
        # 时序修复分支 — 跑 sanity + basic_func 两个用例
        ("br_fix_timing_closure", ["sanity_check", "basic_func"]),
        # 门控时钟修复 — 只跑 sanity
        ("br_fix_clock_gating",   ["sanity_check"]),
    ])
    def test_branch_smoke(self, mock_container, make_plan, branch, cases):
        """指定分支 + 用例子集的 smoke 验证"""
        plan = make_plan("local", branch=branch, cases=cases)
        report = ExecutionOrchestrator(container=mock_container).run(plan)

        assert report.success is True
        assert report.run_id != ""

    def test_default_smoke(self, mock_container, make_plan):
        """模板默认值即可跑通 (不覆盖任何参数)"""
        plan = make_plan("local")
        report = ExecutionOrchestrator(container=mock_container).run(plan)
        assert report.success is True


class TestLocalRegression:
    """本地 PC 全量回归

    验证目标: 不同并行度 / 不同快照版本下的回归执行
    """

    @pytest.mark.parametrize("parallel", [4, 8, 16])
    def test_parallel_scaling(self, mock_container, make_plan, parallel):
        """验证不同并行度下回归执行均能成功"""
        plan = make_plan("local",
                         branch="br_perf_optimization",
                         suite="regression",
                         parallel=parallel,
                         cases=[])  # 空列表 = 执行全部用例
        report = ExecutionOrchestrator(container=mock_container).run(plan)
        assert report.success is True

    @pytest.mark.parametrize("snapshot", ["20250206B003", "20250210B001"])
    def test_snapshot_versions(self, mock_container, make_plan, snapshot):
        """验证切换快照版本后 plan 参数正确绑定"""
        plan = make_plan("local", snapshot_id=snapshot)
        assert plan.snapshot_id == snapshot


# =========================================================================
# 用例 B: 远程服务器执行
#
# 场景: CI 流水线 / Web 看板提交到远程服务器 B 执行
# 模板: "remote" — 远程 SSH 构建 + 远程 EDA 仿真
# =========================================================================


class TestRemote:
    """远程服务器 B 编排执行

    验证目标: 不同分支 / 不同用例集在远程环境下的编排执行
    """

    @pytest.mark.parametrize("branch,cases", [
        # 时序修复 — 基本验证
        ("br_fix_timing_closure", ["sanity_check", "basic_func"]),
        # DFT 扫描链 — 专项用例
        ("br_dft_scan_chain",     ["scan_test_1", "scan_test_2"]),
    ])
    def test_remote_execute(self, mock_container, make_plan, branch, cases):
        """远程编排执行成功且环境被正确释放"""
        plan = make_plan("remote", branch=branch, cases=cases)
        report = ExecutionOrchestrator(container=mock_container).run(plan)

        assert report.success is True
        mock_container.env.release.assert_called_once()

    def test_remote_regression(self, mock_container, make_plan):
        """远程全量回归 — 覆盖 suite 和 parallel"""
        plan = make_plan("remote", suite="regression", parallel=8, cases=[])
        report = ExecutionOrchestrator(container=mock_container).run(plan)
        assert report.success is True


# =========================================================================
# 通用: 编排步骤 & Plan 属性
#
# 不区分 local/remote，验证 7 步编排流水线本身的正确性
# =========================================================================


class TestSteps:
    """验证 7 步编排的完整性 (环境→代码仓→构建→激励→执行→收集→清理)"""

    @pytest.mark.parametrize("tpl", ["local", "remote"])
    def test_all_steps_executed(self, mock_container, make_plan, tpl):
        """7 步流水线的关键步骤全部执行"""
        plan = make_plan(tpl, branch="br_fix_timing_closure")
        report = ExecutionOrchestrator(container=mock_container).run(plan)

        steps = {s["step"] for s in report.steps}
        assert {"provision_env", "checkout", "build", "execute", "collect", "teardown"} <= steps

    @pytest.mark.parametrize("tpl", ["local", "remote"])
    def test_teardown_always_releases(self, mock_container, make_plan, tpl):
        """无论哪种模板，teardown 都必须释放环境资源"""
        plan = make_plan(tpl)
        ExecutionOrchestrator(container=mock_container).run(plan)
        mock_container.env.release.assert_called_once()


class TestPlanConversion:
    """Plan → RunRequest 转换正确性

    OrchestrationPlan 最终会被转换为 RunRequest 交给 runner 执行，
    这里验证转换逻辑的关键字段映射。
    """

    @pytest.mark.parametrize("tpl,expected_env", [
        ("local",  "sim_eda"),         # local 模板 → sim_eda 执行环境
        ("remote", "sim_eda_remote"),   # remote 模板 → sim_eda_remote
    ])
    def test_env_mapping(self, make_plan, tpl, expected_env):
        """模板的 exe_env_name 正确映射到 RunRequest.environment"""
        plan = make_plan(tpl)
        req = plan.to_run_request()
        assert req.environment == expected_env

    def test_branch_override_in_plan(self, make_plan):
        """make_plan 的 branch 语法糖正确展开为 repo_ref_overrides"""
        plan = make_plan("local", branch="br_new_feature")
        assert plan.repo_ref_overrides["rtl_core"] == "br_new_feature"
