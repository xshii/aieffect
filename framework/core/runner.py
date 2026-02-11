"""用例执行器 - 核心执行引擎"""

from __future__ import annotations

import logging
from pathlib import Path

from framework.core.models import Case, SuiteResult, TaskResult
from framework.core.scheduler import Scheduler
from framework.utils.yaml_io import load_yaml

logger = logging.getLogger(__name__)


class CaseRunner:
    """测试套件执行编排器"""

    def __init__(self, config_path: str = "configs/default.yml", parallel: int = 1) -> None:
        from framework.core.config import get_config
        from framework.core.resource import ResourceManager

        self.config = self._load_config(config_path)
        self.parallel = parallel
        cfg = get_config()

        # 从配置中初始化资源管理器
        res_cfg = self.config.get("resource", {})
        resource_mgr = ResourceManager(
            mode=res_cfg.get("mode", cfg.resource_mode),
            capacity=res_cfg.get("max_workers", max(cfg.max_workers, parallel)),
            api_url=res_cfg.get("api_url", cfg.resource_api_url),
        ) if res_cfg else None

        self.scheduler = Scheduler(
            max_workers=parallel,
            resource_manager=resource_mgr,
        )

    @staticmethod
    def _load_config(path: str) -> dict:
        config_file = Path(path)
        if not config_file.exists():
            logger.warning("配置文件 %s 不存在，使用默认配置。", path)
            return {}
        return load_yaml(config_file)

    def load_suite(self, suite_name: str) -> list[Case]:
        """从套件定义文件加载测试用例"""
        from framework.core.config import get_config
        cfg = get_config()
        suite_dir = Path(self.config.get("suite_dir", cfg.suite_dir))
        suite_file = suite_dir / f"{suite_name}.yml"

        if not suite_file.exists():
            logger.error("套件文件不存在: %s", suite_file)
            return []

        data = load_yaml(suite_file)

        cases = []
        for tc in data.get("testcases", []):
            cases.append(
                Case(
                    name=tc["name"],
                    args=tc.get("args", {}),
                    timeout=tc.get("timeout", cfg.default_timeout),
                    tags=tc.get("tags", []),
                    environment=tc.get("environment", ""),
                    repo=tc.get("repo", {}),
                )
            )
        return cases

    @staticmethod
    def _filter_and_prepare(
        cases: list[Case],
        environment: str,
        params: dict[str, str] | None,
    ) -> list[Case]:
        """按环境过滤并注入运行时参数（共用逻辑）"""
        if environment:
            cases = [c for c in cases if not c.environment or c.environment == environment]
            for c in cases:
                c.environment = environment
        if params:
            for c in cases:
                c.params.update(params)
                cmd = c.args.get("cmd", "")
                if cmd:
                    for k, v in params.items():
                        cmd = cmd.replace(f"{{{k}}}", v)
                    c.args["cmd"] = cmd
        return cases

    def run_suite(
        self,
        suite_name: str,
        *,
        environment: str = "",
        params: dict[str, str] | None = None,
        snapshot_id: str = "",
        case_names: list[str] | None = None,
    ) -> SuiteResult:
        """执行套件内所有测试用例"""
        cases = self.load_suite(suite_name)
        if not cases:
            logger.warning("套件 '%s' 中没有找到测试用例。", suite_name)
            return SuiteResult(
                suite_name=suite_name, environment=environment,
                snapshot_id=snapshot_id,
            )

        # 按用例名过滤
        if case_names:
            cases = [c for c in cases if c.name in case_names]
            if not cases:
                logger.warning(
                    "套件 '%s' 中没有匹配的用例: %s",
                    suite_name, case_names,
                )
                return SuiteResult(
                    suite_name=suite_name, environment=environment,
                    snapshot_id=snapshot_id,
                )

        cases = self._filter_and_prepare(cases, environment, params)

        logger.info(
            "运行套件 '%s'，共 %d 个用例（并行度=%d, 环境=%s）",
            suite_name, len(cases), self.parallel, environment or "默认",
        )

        task_results = self.scheduler.run_all(cases)
        return self._build_result(suite_name, environment, snapshot_id, task_results)

    def run_cases(
        self,
        cases: list[Case],
        *,
        suite_name: str = "ad-hoc",
        environment: str = "",
        params: dict[str, str] | None = None,
        snapshot_id: str = "",
    ) -> SuiteResult:
        """直接执行一组 Case（来自 CaseManager.to_test_cases() 或手动构造）"""
        cases = self._filter_and_prepare(cases, environment, params)

        if not cases:
            return SuiteResult(
                suite_name=suite_name, environment=environment,
                snapshot_id=snapshot_id,
            )

        logger.info("运行 %d 个用例（并行度=%d）", len(cases), self.parallel)
        task_results = self.scheduler.run_all(cases)
        return self._build_result(suite_name, environment, snapshot_id, task_results)

    @staticmethod
    def _build_result(
        suite_name: str, environment: str, snapshot_id: str,
        task_results: list[TaskResult],
    ) -> SuiteResult:
        result = SuiteResult.from_tasks(
            task_results,
            suite_name=suite_name,
            environment=environment,
            snapshot_id=snapshot_id,
        )
        logger.info(
            "完成: %d 通过, %d 失败, %d 错误",
            result.passed, result.failed, result.errors,
        )
        return result
