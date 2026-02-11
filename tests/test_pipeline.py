"""ResultPipeline、run_cases、资源卡控 测试"""

from __future__ import annotations

from pathlib import Path

from framework.core.pipeline import ResultPipeline
from framework.core.resource import ResourceManager
from framework.core.runner import Case, CaseRunner, SuiteResult
from framework.core.scheduler import Scheduler, TaskResult


class TestResultPipeline:
    def test_process_saves_results_and_history(self, tmp_path: Path) -> None:
        history_file = str(tmp_path / "history.json")
        result_dir = str(tmp_path / "results")
        pipeline = ResultPipeline(
            history_file=history_file, result_dir=result_dir,
        )

        suite_result = SuiteResult(
            suite_name="demo", total=1, passed=1,
            results=[TaskResult(name="tc1", status="passed", duration=0.5)],
        )
        pipeline.process(suite_result, suite="demo", environment="sim")

        # 验证历史写入
        import json
        records = json.loads(Path(history_file).read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["suite"] == "demo"
        assert records[0]["environment"] == "sim"

    def test_process_empty_results(self, tmp_path: Path) -> None:
        pipeline = ResultPipeline(
            history_file=str(tmp_path / "h.json"),
            result_dir=str(tmp_path / "res"),
        )
        suite_result = SuiteResult(suite_name="empty")
        pipeline.process(suite_result)
        # 不应崩溃


class TestRunCases:
    def test_run_cases_direct(self, tmp_path: Path) -> None:
        import yaml

        config_file = tmp_path / "cfg.yml"
        config_file.write_text(yaml.dump({}), encoding="utf-8")

        runner = CaseRunner(config_path=str(config_file), parallel=1)
        cases = [
            Case(name="echo1", args={"cmd": "echo hello"}),
            Case(name="echo2", args={"cmd": "echo world"}),
        ]
        result = runner.run_cases(cases, suite_name="adhoc")

        assert result.suite_name == "adhoc"
        assert result.total == 2
        assert result.passed == 2

    def test_run_cases_empty(self, tmp_path: Path) -> None:
        import yaml

        config_file = tmp_path / "cfg.yml"
        config_file.write_text(yaml.dump({}), encoding="utf-8")

        runner = CaseRunner(config_path=str(config_file))
        result = runner.run_cases([])
        assert result.total == 0

    def test_run_cases_with_env_filter(self, tmp_path: Path) -> None:
        import yaml

        config_file = tmp_path / "cfg.yml"
        config_file.write_text(yaml.dump({}), encoding="utf-8")

        runner = CaseRunner(config_path=str(config_file))
        cases = [
            Case(name="sim1", args={"cmd": "echo sim"}, environment="sim"),
            Case(name="fpga1", args={"cmd": "echo fpga"}, environment="fpga"),
        ]
        result = runner.run_cases(cases, environment="sim")
        assert result.total == 1
        assert result.results[0].name == "sim1"


class TestResourceGating:
    def test_acquire_release_self_mode(self) -> None:
        rm = ResourceManager(mode="self", capacity=2)
        assert rm.acquire(task_name="t1") is True
        assert rm.acquire(task_name="t2") is True
        assert rm.acquire(task_name="t3") is False  # full

        rm.release(task_name="t1")
        assert rm.acquire(task_name="t3") is True  # now available

    def test_scheduler_skips_on_no_resource(self) -> None:
        rm = ResourceManager(mode="self", capacity=1)
        # Exhaust all capacity
        rm.acquire(task_name="blocker")
        scheduler = Scheduler(max_workers=1, resource_manager=rm)
        case = Case(name="tc1", args={"cmd": "echo hi"})
        results = scheduler.run_all([case])
        assert results[0].status == "skipped"
        assert "资源不足" in results[0].message

    def test_scheduler_without_resource_manager(self) -> None:
        scheduler = Scheduler(max_workers=1, resource_manager=None)
        case = Case(name="tc1", args={"cmd": "echo ok"})
        results = scheduler.run_all([case])
        assert results[0].status == "passed"

    def test_resource_status(self) -> None:
        rm = ResourceManager(mode="self", capacity=4)
        rm.acquire(task_name="a")
        s = rm.status()
        assert s.capacity == 4
        assert s.in_use == 1
        assert s.available == 3
        assert "a" in s.tasks


class TestAtomicWrite:
    def test_save_yaml_atomic(self, tmp_path: Path) -> None:
        from framework.utils.yaml_io import load_yaml, save_yaml

        path = tmp_path / "test.yml"
        save_yaml(path, {"key": "value"})
        data = load_yaml(path)
        assert data["key"] == "value"

    def test_history_atomic_save(self, tmp_path: Path) -> None:
        from framework.core.history import HistoryManager

        hm = HistoryManager(history_file=str(tmp_path / "h.json"))
        hm.record_run("suite1", [{"name": "tc1", "status": "passed"}])
        hm.record_run("suite2", [{"name": "tc2", "status": "failed"}])

        records = hm._load()
        assert len(records) == 2


class TestCaseManagerBridge:
    def test_to_test_cases(self, tmp_path: Path) -> None:
        from framework.core.case_manager import CaseManager

        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("tc1", "echo 1", tags=["smoke"])
        cm.add_case("tc2", "echo 2", tags=["full"])

        cases = cm.to_test_cases()
        assert len(cases) == 2
        assert all(isinstance(c, Case) for c in cases)
        assert cases[0].name == "tc1"
        assert cases[0].args["cmd"] == "echo 1"

    def test_to_test_cases_filter(self, tmp_path: Path) -> None:
        from framework.core.case_manager import CaseManager

        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("tc1", "echo 1", tags=["smoke"])
        cm.add_case("tc2", "echo 2", tags=["full"])

        cases = cm.to_test_cases(tag="smoke")
        assert len(cases) == 1
        assert cases[0].name == "tc1"

    def test_to_test_cases_by_name(self, tmp_path: Path) -> None:
        from framework.core.case_manager import CaseManager

        cm = CaseManager(cases_file=str(tmp_path / "cases.yml"))
        cm.add_case("tc1", "echo 1")
        cm.add_case("tc2", "echo 2")

        cases = cm.to_test_cases(names=["tc2"])
        assert len(cases) == 1
        assert cases[0].name == "tc2"
