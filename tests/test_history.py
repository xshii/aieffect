"""执行历史管理器测试"""

from pathlib import Path

from framework.core.history import HistoryManager


def _sample_results() -> list[dict]:
    return [
        {"name": "tc1", "status": "passed", "duration": 1.0, "message": "ok"},
        {"name": "tc2", "status": "failed", "duration": 2.0, "message": "退出码: 1"},
    ]


class TestHistoryManager:
    def test_record_and_query(self, tmp_path: Path) -> None:
        hm = HistoryManager(history_file=str(tmp_path / "history.json"))
        entry = hm.record_run("default", _sample_results(), environment="sim")

        assert entry["suite"] == "default"
        assert entry["summary"]["total"] == 2
        assert entry["summary"]["passed"] == 1

        records = hm.query()
        assert len(records) == 1

    def test_query_by_suite(self, tmp_path: Path) -> None:
        hm = HistoryManager(history_file=str(tmp_path / "history.json"))
        hm.record_run("smoke", _sample_results())
        hm.record_run("full", _sample_results())

        smoke = hm.query(suite="smoke")
        assert len(smoke) == 1
        assert smoke[0]["suite"] == "smoke"

    def test_query_by_case_name(self, tmp_path: Path) -> None:
        hm = HistoryManager(history_file=str(tmp_path / "history.json"))
        hm.record_run("default", _sample_results())

        tc1 = hm.query(case_name="tc1")
        assert len(tc1) == 1
        assert tc1[0]["results"][0]["name"] == "tc1"

    def test_case_summary(self, tmp_path: Path) -> None:
        hm = HistoryManager(history_file=str(tmp_path / "history.json"))
        hm.record_run("s1", [{"name": "tc1", "status": "passed", "duration": 1.0, "message": ""}])
        hm.record_run("s2", [{"name": "tc1", "status": "failed", "duration": 2.0, "message": "err"}])

        summary = hm.case_summary("tc1")
        assert summary["total_runs"] == 2
        assert summary["passed"] == 1
        assert summary["pass_rate"] == 50.0

    def test_submit_external(self, tmp_path: Path) -> None:
        hm = HistoryManager(history_file=str(tmp_path / "history.json"))
        entry = hm.submit_external({
            "suite": "ext_suite",
            "results": [{"name": "ext1", "status": "passed", "duration": 0.5, "message": ""}],
            "environment": "lab",
        })
        assert entry["suite"] == "ext_suite"
        assert entry["environment"] == "lab"

    def test_submit_external_missing_fields(self, tmp_path: Path) -> None:
        hm = HistoryManager(history_file=str(tmp_path / "history.json"))
        try:
            hm.submit_external({"results": []})
            assert False, "应抛出 ValueError"
        except ValueError:
            pass

    def test_limit(self, tmp_path: Path) -> None:
        hm = HistoryManager(history_file=str(tmp_path / "history.json"))
        for i in range(10):
            hm.record_run(f"s{i}", _sample_results())

        records = hm.query(limit=3)
        assert len(records) == 3
