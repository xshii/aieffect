"""收集器模块的单元测试"""

from __future__ import annotations

import json
from pathlib import Path

from framework.core.pipeline import save_results
from framework.core.scheduler import TaskResult


class TestCollector:
    def test_save_results(self, tmp_path: Path) -> None:
        results = [
            TaskResult(name="case1", status="passed", duration=2.5, message="OK"),
            TaskResult(name="case2", status="failed", duration=1.0, message="assertion error"),
        ]
        paths = save_results(results, output_dir=str(tmp_path / "out"))
        assert len(paths) == 2
        data = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
        assert data["name"] == "case1"
        assert data["status"] == "passed"
        assert data["duration"] == 2.5
