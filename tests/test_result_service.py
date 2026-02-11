"""ResultService 单元测试"""

from __future__ import annotations

import pytest

from framework.core.models import SuiteResult, TaskResult


class TestResultService:
    """结果服务测试"""

    @pytest.fixture()
    def svc(self, tmp_path):
        from framework.services.result_service import ResultService
        return ResultService(
            result_dir=str(tmp_path / "results"),
            history_file=str(tmp_path / "history.json"),
        )

    def _make_suite_result(self) -> SuiteResult:
        return SuiteResult.from_tasks(
            [
                TaskResult(name="test_a", status="passed", duration=1.0, message="ok"),
                TaskResult(name="test_b", status="failed", duration=2.0, message="assert error"),
                TaskResult(name="test_c", status="passed", duration=0.5, message="ok"),
            ],
            suite_name="smoke",
            environment="sim",
        )

    def test_save_and_list(self, svc, tmp_path):
        sr = self._make_suite_result()
        run_id = svc.save(sr)
        assert run_id != ""

        # 验证 JSON 文件已写入
        results_dir = tmp_path / "results"
        assert (results_dir / "test_a.json").exists()
        assert (results_dir / "test_b.json").exists()

        data = svc.list_results()
        assert data["summary"]["total"] == 3
        assert data["summary"]["passed"] == 2
        assert data["summary"]["failed"] == 1

    def test_get_result(self, svc, tmp_path):
        sr = self._make_suite_result()
        svc.save(sr)

        r = svc.get_result("test_a")
        assert r is not None
        assert r["status"] == "passed"

        assert svc.get_result("nonexistent") is None

    def test_query_history(self, svc):
        sr = self._make_suite_result()
        svc.save(sr, suite="smoke", environment="sim")

        records = svc.query_history(suite="smoke")
        assert len(records) == 1
        assert records[0]["suite"] == "smoke"

    def test_case_summary(self, svc):
        sr = self._make_suite_result()
        svc.save(sr)

        summary = svc.case_summary("test_a")
        assert summary["total_runs"] == 1
        assert summary["passed"] == 1
        assert summary["pass_rate"] == 100.0

    def test_compare_runs(self, svc):
        sr1 = self._make_suite_result()
        run_id_1 = svc.save(sr1)

        sr2 = SuiteResult.from_tasks(
            [
                TaskResult(name="test_a", status="passed", duration=1.0),
                TaskResult(name="test_b", status="passed", duration=1.5),  # 变化
                TaskResult(name="test_c", status="failed", duration=3.0),  # 变化
            ],
            suite_name="smoke",
        )
        run_id_2 = svc.save(sr2)

        diff = svc.compare_runs(run_id_1, run_id_2)
        assert diff["total_cases"] == 3
        assert diff["changed_cases"] == 2

    def test_compare_missing_run(self, svc):
        diff = svc.compare_runs("aaa", "bbb")
        assert "error" in diff

    def test_clean_results(self, svc, tmp_path):
        sr = self._make_suite_result()
        svc.save(sr)

        count = svc.clean_results()
        assert count == 3
        assert svc.list_results()["summary"]["total"] == 0
