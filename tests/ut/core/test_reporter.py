"""报告生成器的单元测试"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.core.reporter import generate_report


@pytest.fixture()
def result_dir(tmp_path: Path) -> Path:
    rdir = tmp_path / "results"
    rdir.mkdir()
    for name, status in [("case1", "passed"), ("case2", "failed"), ("case3", "passed")]:
        (rdir / f"{name}.json").write_text(
            json.dumps({"name": name, "status": status, "duration": 1.0, "message": ""}),
            encoding="utf-8",
        )
    return rdir


class TestReporter:
    def test_gen_json(self, result_dir: Path) -> None:
        output = generate_report(result_dir=str(result_dir), fmt="json")
        assert output.endswith("report.json")
        report = json.loads(Path(output).read_text(encoding="utf-8"))
        assert report["summary"]["total"] == 3
        assert report["summary"]["passed"] == 2

    def test_gen_html(self, result_dir: Path) -> None:
        output = generate_report(result_dir=str(result_dir), fmt="html")
        assert output.endswith("report.html")
        html = Path(output).read_text(encoding="utf-8")
        assert "case1" in html and "case2" in html

    def test_gen_junit(self, result_dir: Path) -> None:
        output = generate_report(result_dir=str(result_dir), fmt="junit")
        assert output.endswith("report.xml")
        xml = Path(output).read_text(encoding="utf-8")
        assert 'tests="3"' in xml and 'failures="1"' in xml

    def test_empty_results(self, tmp_path: Path) -> None:
        output = generate_report(result_dir=str(tmp_path / "nonexistent"), fmt="json")
        assert output == ""
