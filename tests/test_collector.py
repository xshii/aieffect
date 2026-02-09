"""收集器模块的单元测试"""

from __future__ import annotations

import json
from pathlib import Path

from framework.core.collector import Collector
from framework.core.scheduler import TaskResult


class TestCollector:
    def test_save_result(self, tmp_path: Path) -> None:
        collector = Collector(output_dir=str(tmp_path / "out"))
        result = TaskResult(name="case1", status="passed", duration=2.5, message="OK")
        path = collector.save_result(result)
        data = json.loads(Path(path).read_text())
        assert data["name"] == "case1"
        assert data["status"] == "passed"
        assert data["duration"] == 2.5

    def test_save_multiple(self, tmp_path: Path) -> None:
        collector = Collector(output_dir=str(tmp_path / "out"))
        results = [
            TaskResult(name="a", status="passed", duration=1.0),
            TaskResult(name="b", status="failed", duration=2.0, message="assertion error"),
        ]
        paths = collector.save_results(results)
        assert len(paths) == 2
