"""Demo 测试套共享 fixture — 模板加载 + mock 服务"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from framework.services.execution_orchestrator import OrchestrationPlan

# =========================================================================
# 模板加载
# =========================================================================

_TEMPLATES: dict[str, dict] = yaml.safe_load(
    (Path(__file__).parent / "scenarios.yml").read_text(encoding="utf-8"),
)


def _make_plan(
    template: str,
    *,
    branch: str = "",
    cases: list[str] | None = None,
    **overrides: object,
) -> OrchestrationPlan:
    """从模板构建 Plan，用关键字参数覆盖差异部分。

    用法:
        make_plan("local", branch="br_fix", cases=["tc1"])
        make_plan("remote", parallel=8, suite="regression")
    """
    t = deepcopy(_TEMPLATES[template])

    # 语法糖: branch → repo_ref_overrides (第一个 repo)
    if branch:
        repo = t["repo_names"][0]
        overrides.setdefault("repo_ref_overrides", {repo: branch})

    # 语法糖: cases → case_names
    if cases is not None:
        overrides.setdefault("case_names", cases)

    t.update(overrides)

    return OrchestrationPlan(
        suite=t.get("suite", "default"),
        parallel=t.get("parallel", 1),
        build_env_name=t.get("build_env_name", ""),
        exe_env_name=t.get("exe_env_name", ""),
        repo_names=t.get("repo_names", []),
        repo_ref_overrides=t.get("repo_ref_overrides", {}),
        build_names=t.get("build_names", []),
        snapshot_id=t.get("snapshot_id", ""),
        case_names=t.get("case_names", []),
        params={"VERSION": t.get("snapshot_id", "")},
    )


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture()
def make_plan():
    """返回 plan 工厂函数，测试里直接调用即可。"""
    return _make_plan


@pytest.fixture()
def mock_container():
    """mock ServiceContainer — 7 步编排可直接执行"""
    c = MagicMock()

    session = MagicMock()
    session.status = "applied"
    session.session_id = "test-session"
    session.resolved_vars = {"CC": "gcc"}
    session.work_dir = "/tmp/work"
    session.name = "mock_env"
    c.env.apply.return_value = session

    ws = MagicMock()
    ws.spec.name = "rtl_core"
    ws.status = "cloned"
    c.repo.checkout.return_value = ws

    br = MagicMock()
    br.spec.name = "rtl_build"
    br.status = "success"
    c.build.build.return_value = br

    sr = MagicMock()
    sr.total, sr.passed, sr.failed, sr.errors = 2, 2, 0, 0
    sr.success = True
    c.run.execute.return_value = sr

    c.result.save.return_value = "run-demo-001"

    return c
