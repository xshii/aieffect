"""参数化验证场景 Demo — 用例 A & B

场景由 scenarios.yml 驱动，通过 conftest fixture 注入 mock 服务。
每个测试只关注「验证什么」，不关注「怎么注册」。

运行:
  pytest demos/ -v                   # 全部
  pytest demos/ -k "smoke" -v        # smoke
  pytest demos/ -k "remote" -v       # 远程场景(用例B)
"""

from __future__ import annotations

import pytest

from demos.conftest import scenario_params
from framework.services.execution_orchestrator import (
    ExecutionOrchestrator,
    OrchestrationPlan,
)


def _plan_from_cfg(cfg: dict) -> OrchestrationPlan:
    """从 YAML 场景配置构建 OrchestrationPlan"""
    p = cfg["plan"]
    return OrchestrationPlan(
        suite=p["suite"],
        parallel=p.get("parallel", 1),
        build_env_name=p.get("build_env_name", ""),
        exe_env_name=p.get("exe_env_name", ""),
        repo_names=p.get("repo_names", []),
        repo_ref_overrides=p.get("repo_ref_overrides", {}),
        build_names=p.get("build_names", []),
        snapshot_id=cfg.get("snapshot_id", ""),
        case_names=p.get("case_names", []),
        params={"VERSION": cfg.get("snapshot_id", "")},
    )


class TestOrchestrate:
    """核心: 7 步编排执行"""

    @pytest.mark.parametrize("cfg", scenario_params())
    def test_full_pipeline(self, mock_container, cfg: dict):
        """编排执行完成且成功"""
        plan = _plan_from_cfg(cfg)
        report = ExecutionOrchestrator(container=mock_container).run(plan)

        assert report.success is True
        assert report.run_id != ""

    @pytest.mark.parametrize("cfg", scenario_params())
    def test_all_steps_executed(self, mock_container, cfg: dict):
        """7 步全部执行"""
        plan = _plan_from_cfg(cfg)
        report = ExecutionOrchestrator(container=mock_container).run(plan)

        steps = {s["step"] for s in report.steps}
        assert {"provision_env", "checkout", "build", "execute", "collect", "teardown"} <= steps

    @pytest.mark.parametrize("cfg", scenario_params())
    def test_teardown_releases_env(self, mock_container, cfg: dict):
        """环境一定被释放"""
        plan = _plan_from_cfg(cfg)
        ExecutionOrchestrator(container=mock_container).run(plan)

        mock_container.env.release.assert_called_once()


class TestPlanParams:
    """验证编排计划的参数传递"""

    @pytest.mark.parametrize("cfg", scenario_params())
    def test_snapshot_bound(self, cfg: dict):
        """快照 ID 绑定正确"""
        plan = _plan_from_cfg(cfg)
        assert plan.snapshot_id == cfg["snapshot_id"]

    @pytest.mark.parametrize("cfg", scenario_params())
    def test_branch_override(self, cfg: dict):
        """分支覆盖正确传递"""
        plan = _plan_from_cfg(cfg)
        overrides = cfg["plan"].get("repo_ref_overrides", {})
        for repo, branch in overrides.items():
            assert plan.repo_ref_overrides[repo] == branch

    @pytest.mark.parametrize("cfg", scenario_params())
    def test_run_request_conversion(self, cfg: dict):
        """Plan → RunRequest 转换正确"""
        plan = _plan_from_cfg(cfg)
        req = plan.to_run_request()
        assert req.suite == cfg["plan"]["suite"]
        assert req.environment == cfg["plan"].get("exe_env_name", "")


class TestUpload:
    """结果上传配置验证"""

    @pytest.mark.parametrize("cfg", scenario_params())
    def test_upload_config_present(self, cfg: dict):
        """上传配置存在"""
        upload = cfg.get("upload", {})
        assert upload.get("type") in ("rsync", "api", "local", None)

    @pytest.mark.parametrize(
        "cfg",
        [c for _, c in __import__("demos.conftest", fromlist=["ALL_SCENARIOS"]).ALL_SCENARIOS
         if c.get("export")],
        ids=lambda c: c.get("plan", {}).get("suite", "?"),
    )
    def test_export_format(self, cfg: dict):
        """用例B: 导出格式配置正确"""
        assert cfg["export"]["format"] in ("html", "json", "junit")
