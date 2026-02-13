"""结果处理管线（Observer 模式）

内置 save_results + record_history 两个核心步骤，
同时支持通过 subscribe() 注册自定义观察者钩子（通知、指标、告警等），
做到对扩展开放、对修改关闭。

用法:
    pipeline = ResultPipeline()
    pipeline.subscribe(my_notifier)         # 注册自定义钩子
    pipeline.process(suite_result, suite="default", environment="sim")
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from framework.core.history import HistoryManager
from framework.core.models import SuiteResult

if TYPE_CHECKING:
    from framework.core.models import TaskResult

logger = logging.getLogger(__name__)


def save_results(results: list[TaskResult], output_dir: str = "") -> list[str]:
    """批量保存测试结果为 JSON 文件（原 collector.py 内联）"""
    if not output_dir:
        from framework.core.config import get_config
        output_dir = get_config().result_dir
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for r in results:
        f = out / f"{r.name}.json"
        f.write_text(json.dumps(asdict(r), indent=2), encoding="utf-8")
        paths.append(str(f))
    logger.info("已保存 %d 条结果到 %s", len(paths), out)
    return paths


class PipelineHook(ABC):
    """管线观察者钩子基类，实现 on_result 即可接入管线"""

    @abstractmethod
    def on_result(self, suite_result: SuiteResult, context: dict) -> None:
        """接收执行结果和上下文信息"""


class ResultPipeline:
    """执行结果后处理管线"""

    def __init__(
        self,
        history_file: str = "",
        result_dir: str = "",
    ) -> None:
        self.history = HistoryManager(history_file=history_file)
        if not result_dir:
            from framework.core.config import get_config
            result_dir = get_config().result_dir
        self.result_dir = result_dir
        self._hooks: list[PipelineHook] = []

    def subscribe(self, hook: PipelineHook) -> None:
        """注册后处理钩子"""
        self._hooks.append(hook)

    def process(
        self,
        suite_result: SuiteResult,
        *,
        suite: str = "",
        environment: str = "",
        snapshot_id: str = "",
        params: dict[str, str] | None = None,
    ) -> None:
        """对一次执行结果执行全部后处理步骤"""
        suite_name = suite or suite_result.suite_name

        # 1. 持久化结果 JSON
        if suite_result.results:
            save_results(suite_result.results, output_dir=self.result_dir)

        # 2. 记录到执行历史
        self.history.record_run(
            suite=suite_name,
            results=[asdict(r) for r in suite_result.results],
            environment=environment or suite_result.environment,
            snapshot_id=snapshot_id or suite_result.snapshot_id,
            params=params,
        )

        # 3. 通知所有观察者
        context = {
            "suite": suite_name,
            "environment": environment or suite_result.environment,
            "snapshot_id": snapshot_id or suite_result.snapshot_id,
            "params": params,
        }
        for hook in self._hooks:
            try:
                hook.on_result(suite_result, context)
            except (ValueError, RuntimeError, OSError, TypeError):
                logger.exception("管线钩子执行失败: %s", type(hook).__name__)

        logger.info(
            "结果管线完成: suite=%s, 通过=%d, 失败=%d, 错误=%d",
            suite_name, suite_result.passed,
            suite_result.failed, suite_result.errors,
        )
