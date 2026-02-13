"""Demo 测试套的共享 fixture — 加载场景 & mock 外部服务"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml


# =========================================================================
# 场景数据加载
# =========================================================================

SCENARIOS_FILE = Path(__file__).parent / "scenarios.yml"


def _load_scenarios() -> list[tuple[str, dict]]:
    """从 YAML 加载全部场景配置"""
    data = yaml.safe_load(SCENARIOS_FILE.read_text(encoding="utf-8"))
    return [(name, cfg) for name, cfg in data.items()]


ALL_SCENARIOS = _load_scenarios()


def scenario_ids() -> list[str]:
    return [name for name, _ in ALL_SCENARIOS]


def scenario_params():
    return [pytest.param(cfg, id=name) for name, cfg in ALL_SCENARIOS]


# =========================================================================
# 共享 fixture
# =========================================================================


@pytest.fixture()
def mock_container():
    """构造一个 mock ServiceContainer，7 步编排可直接执行"""
    c = MagicMock()

    # 环境 apply → 返回 mock session
    session = MagicMock()
    session.status = "applied"
    session.session_id = "test-session"
    session.resolved_vars = {"CC": "gcc"}
    session.work_dir = "/tmp/work"
    session.name = "mock_env"
    c.env.apply.return_value = session

    # 代码仓 checkout
    ws = MagicMock()
    ws.spec.name = "rtl_core"
    ws.status = "cloned"
    c.repo.checkout.return_value = ws

    # 构建
    br = MagicMock()
    br.spec.name = "rtl_build"
    br.status = "success"
    c.build.build.return_value = br

    # 执行结果
    sr = MagicMock()
    sr.total, sr.passed, sr.failed, sr.errors = 2, 2, 0, 0
    sr.success = True
    c.run.execute.return_value = sr

    # 结果保存
    c.result.save.return_value = "run-demo-001"

    return c
