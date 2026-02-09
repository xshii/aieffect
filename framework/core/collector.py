"""结果与覆盖率收集器"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.core.scheduler import TaskResult

logger = logging.getLogger(__name__)


class Collector:
    """收集并持久化测试结果和覆盖率数据"""

    def __init__(self, output_dir: str = "results") -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def save_result(self, result: TaskResult) -> str:
        """保存单个测试结果为 JSON 文件"""
        output_file = self.output_dir / f"{result.name}.json"
        with open(output_file, "w") as f:
            json.dump(asdict(result), f, indent=2)
        logger.debug("Result saved: %s", output_file)
        return str(output_file)

    def save_results(self, results: list[TaskResult]) -> list[str]:
        """批量保存测试结果"""
        return [self.save_result(r) for r in results]

    def merge_coverage(self, coverage_files: list[str], output: str = "merged_coverage") -> str:
        """合并多次运行的覆盖率数据库

        此处为占位实现，实际合并依赖具体 EDA 工具。
        VCS 使用 `urg`，Xcelium 使用 `imc`，等等。
        """
        output_path = self.output_dir / output
        output_path.mkdir(parents=True, exist_ok=True)

        manifest = {
            "sources": coverage_files,
            "output": str(output_path),
            "status": "占位 - 需按 EDA 工具实现",
        }

        manifest_file = output_path / "manifest.json"
        with open(manifest_file, "w") as f:
            json.dump(manifest, f, indent=2)

        logger.info("Coverage merge manifest written to %s", manifest_file)
        return str(manifest_file)
