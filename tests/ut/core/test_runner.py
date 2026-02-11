"""用例执行器和调度器的单元测试"""

from __future__ import annotations

from pathlib import Path

import yaml

from framework.core.runner import Case, CaseRunner, SuiteResult
from framework.core.scheduler import TaskResult


class TestCaseDataclass:
    def test_default_values(self) -> None:
        tc = Case(name="foo")
        assert tc.name == "foo"
        assert tc.timeout == 3600
        assert tc.tags == []
        assert tc.args == {}
        assert tc.repo == {}
        assert tc.environment == ""
        assert tc.params == {}

    def test_repo_field(self) -> None:
        tc = Case(name="repo_case", repo={"url": "https://example.com/repo.git", "ref": "v1.0"})
        assert tc.repo["url"] == "https://example.com/repo.git"
        assert tc.repo["ref"] == "v1.0"


class TestSuiteResult:
    def test_empty_suite_is_success(self) -> None:
        r = SuiteResult(suite_name="empty")
        assert r.success is True

    def test_failed_suite(self) -> None:
        r = SuiteResult(suite_name="test", total=2, passed=1, failed=1)
        assert r.success is False

    def test_error_suite(self) -> None:
        r = SuiteResult(suite_name="test", total=1, passed=0, errors=1)
        assert r.success is False


class TestSuiteResultFromTasks:
    def test_from_tasks_counts(self) -> None:
        tasks = [
            TaskResult(name="a", status="passed"),
            TaskResult(name="b", status="failed"),
            TaskResult(name="c", status="error"),
            TaskResult(name="d", status="passed"),
        ]
        result = SuiteResult.from_tasks(tasks, suite_name="s1", environment="sim")
        assert result.total == 4
        assert result.passed == 2
        assert result.failed == 1
        assert result.errors == 1
        assert result.suite_name == "s1"
        assert result.environment == "sim"
        assert result.success is False

    def test_from_tasks_empty(self) -> None:
        result = SuiteResult.from_tasks([], suite_name="empty")
        assert result.total == 0
        assert result.success is True


class TestTaskResult:
    def test_result_fields(self) -> None:
        r = TaskResult(name="case1", status="passed", duration=1.5)
        assert r.name == "case1"
        assert r.status == "passed"
        assert r.duration == 1.5
        assert r.message == ""


class TestLoadSuiteErrors:
    def test_missing_suite_file(self, tmp_path: Path) -> None:
        """套件文件不存在时返回空列表"""
        config_file = tmp_path / "cfg.yml"
        config_file.write_text(yaml.dump({"suite_dir": str(tmp_path / "suites")}))
        runner = CaseRunner(config_path=str(config_file), parallel=1)
        cases = runner.load_suite("nonexistent")
        assert cases == []

    def test_missing_config_file(self, tmp_path: Path) -> None:
        """配置文件不存在时使用默认配置"""
        runner = CaseRunner(config_path=str(tmp_path / "nope.yml"), parallel=1)
        assert runner.config == {}

    def test_run_suite_empty_returns_zero(self, tmp_path: Path) -> None:
        """空套件执行返回 total=0"""
        config_file = tmp_path / "cfg.yml"
        config_file.write_text(yaml.dump({"suite_dir": str(tmp_path / "suites")}))
        runner = CaseRunner(config_path=str(config_file), parallel=1)
        result = runner.run_suite("nonexistent")
        assert result.total == 0
