"""测试调度器 - 管理用例的并行执行"""

from __future__ import annotations

import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.core.runner import TestCase

logger = logging.getLogger(__name__)


@dataclass
class TaskResult:
    """单个测试用例的执行结果"""

    name: str
    status: str  # "passed", "failed", "error", "skipped"
    duration: float = 0.0  # 秒
    message: str = ""
    log_path: str = ""


class Scheduler:
    """可配置并行度的测试调度器"""

    def __init__(self, max_workers: int = 1) -> None:
        self.max_workers = max(1, max_workers)

    def _execute_one(self, case: TestCase) -> TaskResult:
        """通过 shell 命令执行单个测试用例"""
        start = time.monotonic()
        try:
            cmd = case.args.get("cmd", "")
            if not cmd:
                return TaskResult(
                    name=case.name,
                    status="skipped",
                    message="用例 args 中未定义 'cmd' 命令",
                )

            logger.info("执行: %s -> %s", case.name, cmd)
            result = subprocess.run(
                cmd, shell=True, capture_output=True, text=True, timeout=case.timeout
            )
            duration = time.monotonic() - start

            success = result.returncode == 0
            message = "通过" if success else f"退出码: {result.returncode}\n{result.stderr[:500]}"
            return TaskResult(
                name=case.name,
                status="passed" if success else "failed",
                duration=duration,
                message=message,
            )
        except subprocess.TimeoutExpired:
            duration = time.monotonic() - start
            return TaskResult(
                name=case.name,
                status="error",
                duration=duration,
                message=f"超时（{case.timeout}秒）",
            )
        except Exception as e:
            duration = time.monotonic() - start
            logger.exception("执行用例 '%s' 时出错", case.name)
            return TaskResult(
                name=case.name,
                status="error",
                duration=duration,
                message=str(e),
            )

    def run_all(self, cases: list[TestCase]) -> list[TaskResult]:
        """并行控制下执行所有用例"""
        results: list[TaskResult] = []

        if self.max_workers == 1:
            for case in cases:
                logger.info("执行: %s", case.name)
                results.append(self._execute_one(case))
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_map = {executor.submit(self._execute_one, c): c for c in cases}
                for future in as_completed(future_map):
                    case = future_map[future]
                    result = future.result()
                    logger.info("完成: %s -> %s (%.1f秒)", case.name, result.status, result.duration)
                    results.append(result)

        return results
