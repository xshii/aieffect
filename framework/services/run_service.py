"""执行服务 — CLI 和 Web 共享的运行逻辑

将「创建 Runner → 执行套件 → 后处理」的编排逻辑从 CLI/Web 中提取出来，
实现单一入口，避免两处各自实现相同流程。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from framework.core.models import SuiteResult
from framework.core.pipeline import ResultPipeline
from framework.core.runner import CaseRunner

logger = logging.getLogger(__name__)


@dataclass
class RunRequest:
    """执行请求 DTO"""

    suite: str = "default"
    config_path: str = "configs/default.yml"
    parallel: int = 1
    environment: str = ""
    params: dict[str, str] | None = None
    snapshot_id: str = ""
    case_names: list[str] | None = None


class RunService:
    """测试执行服务

    只负责执行用例并返回 SuiteResult，
    结果持久化由上层（Orchestrator 或 CLI）决定。
    """

    def __init__(
        self,
        pipeline: ResultPipeline,
    ) -> None:
        self.pipeline = pipeline

    def execute(self, req: RunRequest) -> SuiteResult:
        """执行套件并返回结果（不自动持久化）"""
        runner = CaseRunner(
            config_path=req.config_path, parallel=req.parallel,
        )
        return runner.run_suite(
            req.suite,
            environment=req.environment,
            params=req.params,
            snapshot_id=req.snapshot_id,
            case_names=req.case_names,
        )

    def execute_and_persist(self, req: RunRequest) -> SuiteResult:
        """执行套件 + 后处理持久化（独立调用入口）"""
        result = self.execute(req)
        self.pipeline.process(
            result,
            suite=req.suite,
            environment=req.environment,
            snapshot_id=req.snapshot_id,
            params=req.params,
        )
        return result
