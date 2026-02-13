"""编排器数据模型

数据类：
- OrchestrationPlan: 编排计划
- OrchestrationReport: 编排报告
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from framework.core.models import ExecutionContext, SuiteResult
from framework.services.run_service import RunRequest


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
