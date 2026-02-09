"""用例执行器 - 核心执行引擎"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from framework.core.scheduler import Scheduler, TaskResult

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    """单个测试用例定义"""

    name: str
    args: dict[str, str] = field(default_factory=dict)
    timeout: int = 3600  # 秒
    tags: list[str] = field(default_factory=list)


@dataclass
class SuiteResult:
    """测试套件执行结果汇总"""

    suite_name: str
    total: int = 0
    passed: int = 0
    failed: int = 0
    errors: int = 0
    results: list[TaskResult] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return self.failed == 0 and self.errors == 0


class TestRunner:
    """测试套件执行编排器"""

    def __init__(self, config_path: str = "configs/default.yml", parallel: int = 1) -> None:
        self.config = self._load_config(config_path)
        self.parallel = parallel
        self.scheduler = Scheduler(max_workers=parallel)

    def _load_config(self, path: str) -> dict:
        config_file = Path(path)
        if not config_file.exists():
            logger.warning("配置文件 %s 不存在，使用默认配置。", path)
            return {}
        with open(config_file) as f:
            return yaml.safe_load(f) or {}

    def load_suite(self, suite_name: str) -> list[TestCase]:
        """从套件定义文件加载测试用例"""
        suite_dir = Path(self.config.get("suite_dir", "testdata/configs"))
        suite_file = suite_dir / f"{suite_name}.yml"

        if not suite_file.exists():
            logger.error("套件文件不存在: %s", suite_file)
            return []

        with open(suite_file) as f:
            data = yaml.safe_load(f) or {}

        cases = []
        for tc in data.get("testcases", []):
            cases.append(
                TestCase(
                    name=tc["name"],
                    args=tc.get("args", {}),
                    timeout=tc.get("timeout", 3600),
                    tags=tc.get("tags", []),
                )
            )
        return cases

    def run_suite(self, suite_name: str) -> SuiteResult:
        """执行套件内所有测试用例"""
        cases = self.load_suite(suite_name)
        if not cases:
            logger.warning("套件 '%s' 中没有找到测试用例。", suite_name)
            return SuiteResult(suite_name=suite_name)

        logger.info("运行套件 '%s'，共 %d 个用例（并行度=%d）", suite_name, len(cases), self.parallel)

        task_results = self.scheduler.run_all(cases)

        result = SuiteResult(
            suite_name=suite_name,
            total=len(task_results),
            passed=sum(1 for r in task_results if r.status == "passed"),
            failed=sum(1 for r in task_results if r.status == "failed"),
            errors=sum(1 for r in task_results if r.status == "error"),
            results=task_results,
        )

        logger.info(
            "套件 '%s' 完成: %d 通过, %d 失败, %d 错误",
            suite_name,
            result.passed,
            result.failed,
            result.errors,
        )
        return result
