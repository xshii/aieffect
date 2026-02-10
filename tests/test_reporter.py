"""报告生成器的单元测试"""

from __future__ import annotations

import json
from pathlib import Path

from framework.core.reporter import generate_report


def _create_results(tmp_path: Path) -> Path:
    """创建用于测试的示例结果文件"""
    result_dir = tmp_path / "results"
    result_dir.mkdir()

    for name, status in [("case1", "passed"), ("case2", "failed"), ("case3", "passed")]:
        data = {"name": name, "status": status, "duration": 1.0, "message": ""}
        (result_dir / f"{name}.json").write_text(json.dumps(data))

    return result_dir


class TestReporter:
    def test_gen_json(self, tmp_path: Path) -> None:
        result_dir = _create_results(tmp_path)
        output = generate_report(result_dir=str(result_dir), fmt="json")
        assert output.endswith("report.json")
        report = json.loads(Path(output).read_text())
        assert report["summary"]["total"] == 3
        assert report["summary"]["passed"] == 2
        assert report["summary"]["failed"] == 1

    def test_gen_html(self, tmp_path: Path) -> None:
        result_dir = _create_results(tmp_path)
        output = generate_report(result_dir=str(result_dir), fmt="html")
        assert output.endswith("report.html")
        html = Path(output).read_text()
        assert "case1" in html
        assert "case2" in html

    def test_gen_junit(self, tmp_path: Path) -> None:
        result_dir = _create_results(tmp_path)
        output = generate_report(result_dir=str(result_dir), fmt="junit")
        assert output.endswith("report.xml")
        xml = Path(output).read_text()
        assert 'tests="3"' in xml
        assert 'failures="1"' in xml

    def test_empty_results(self, tmp_path: Path) -> None:
        output = generate_report(result_dir=str(tmp_path / "nonexistent"), fmt="json")
        assert output == ""
