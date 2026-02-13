"""Demo 测试套共享 fixture — 模板加载 + mock 服务

整体架构:

  scenarios.yml          conftest.py              test_demo_scenarios.py
  ┌───────────┐     ┌──────────────────┐     ┌──────────────────────────┐
  │ local:    │────>│ _make_plan()     │<────│ make_plan("local",       │
  │   suite   │     │   加载模板       │     │   branch="br_fix",       │
  │   env     │     │   合并 overrides │     │   cases=["tc1"])         │
  │   ...     │     │   构建 Plan      │     │                          │
  │           │     ├──────────────────┤     │ report = Orchestrator    │
  │ remote:   │────>│ mock_container() │────>│   .run(plan)             │
  │   suite   │     │   mock 7步服务   │     │ assert report.success    │
  │   env     │     └──────────────────┘     └──────────────────────────┘
  │   ...     │
  └───────────┘

使用流程:
  1. YAML 模板定义环境基线 (local / remote)
  2. conftest 提供 make_plan fixture，支持 branch/cases 语法糖 + **overrides
  3. 测试用例用 @pytest.mark.parametrize 只写差异参数
  4. mock_container 模拟 7 步编排的所有外部依赖，无需真实 IO
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from framework.services.execution_orchestrator import OrchestrationPlan

# =========================================================================
# 模板加载 — 从 scenarios.yml 读取 local / remote 两套基线配置
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
    """从模板构建 OrchestrationPlan，用关键字参数覆盖差异部分。

    Args:
        template: 模板名，对应 scenarios.yml 中的顶层 key ("local" / "remote")
        branch:   语法糖 — 自动展开为 repo_ref_overrides={第一个repo: branch}
        cases:    语法糖 — 自动展开为 case_names=[...]，空列表表示全部用例
        **overrides: 任意 OrchestrationPlan 字段，直接覆盖模板中的同名字段

    Returns:
        构建好的 OrchestrationPlan 实例

    Examples:
        # 本地 smoke，指定分支和用例
        make_plan("local", branch="br_fix_timing", cases=["sanity_check"])

        # 远程全量回归，覆盖并行度
        make_plan("remote", suite="regression", parallel=16, cases=[])

        # 切换快照版本
        make_plan("local", snapshot_id="20250210B001")
    """
    t = deepcopy(_TEMPLATES[template])

    # 语法糖: branch → repo_ref_overrides (自动绑定到模板中的第一个 repo)
    if branch:
        repo = t["repo_names"][0]
        overrides.setdefault("repo_ref_overrides", {repo: branch})

    # 语法糖: cases → case_names
    if cases is not None:
        overrides.setdefault("case_names", cases)

    # 合并覆盖参数 — overrides 中的 key 会覆盖模板中的同名 key
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
# Fixtures — pytest 自动注入到测试函数参数
# =========================================================================


@pytest.fixture()
def make_plan():
    """Plan 工厂 fixture — 测试用例直接调用构建编排计划。

    用法 (在测试函数签名里声明即可):
        def test_xxx(self, mock_container, make_plan):
            plan = make_plan("local", branch="br_fix")
    """
    return _make_plan


@pytest.fixture()
def mock_container():
    """Mock ServiceContainer — 模拟 7 步编排的全部外部服务。

    模拟的服务链:
      env.apply()       → 返回 mock EnvSession (status="applied")
      repo.checkout()   → 返回 mock Workspace  (status="cloned")
      build.build()     → 返回 mock BuildResult (status="success")
      run.execute()     → 返回 mock SuiteResult (2 passed, 0 failed)
      result.save()     → 返回 run_id "run-demo-001"
      env.release()     → 释放环境 (可用 assert_called_once 验证)
    """
    c = MagicMock()

    # 步骤 1: 环境准备 — apply 返回 mock session
    session = MagicMock()
    session.status = "applied"
    session.session_id = "test-session"
    session.resolved_vars = {"CC": "gcc"}
    session.work_dir = "/tmp/work"
    session.name = "mock_env"
    c.env.apply.return_value = session

    # 步骤 2: 代码仓 checkout
    ws = MagicMock()
    ws.spec.name = "rtl_core"
    ws.status = "cloned"
    c.repo.checkout.return_value = ws

    # 步骤 3: 构建编译
    br = MagicMock()
    br.spec.name = "rtl_build"
    br.status = "success"
    c.build.build.return_value = br

    # 步骤 4-5: 执行 + 收集结果
    sr = MagicMock()
    sr.total, sr.passed, sr.failed, sr.errors = 2, 2, 0, 0
    sr.success = True
    c.run.execute.return_value = sr

    # 步骤 6: 结果保存 → 返回 run_id
    c.result.save.return_value = "run-demo-001"

    # 步骤 7: teardown 由 env.release() 完成 (测试可 assert 是否被调用)

    return c
