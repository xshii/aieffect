"""结果收集器 - 持久化测试结果为 JSON"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.core.scheduler import TaskResult

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = "results"


def save_results(results: list[TaskResult], output_dir: str = DEFAULT_OUTPUT_DIR) -> list[str]:
    """批量保存测试结果为 JSON 文件"""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for r in results:
        f = out / f"{r.name}.json"
        f.write_text(json.dumps(asdict(r), indent=2))
        paths.append(str(f))
    logger.info("已保存 %d 条结果到 %s", len(paths), out)
    return paths
