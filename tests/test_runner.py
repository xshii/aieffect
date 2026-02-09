"""用例执行器和调度器的单元测试"""

from __future__ import annotations

from framework.core.runner import SuiteResult, TestCase
from framework.core.scheduler import TaskResult


class TestTestCase:
    def test_default_values(self) -> None:
        tc = TestCase(name="foo")
        assert tc.name == "foo"
        assert tc.timeout == 3600
        assert tc.tags == []
        assert tc.args == {}


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


class TestTaskResult:
    def test_result_fields(self) -> None:
        r = TaskResult(name="case1", status="passed", duration=1.5)
        assert r.name == "case1"
        assert r.status == "passed"
        assert r.duration == 1.5
        assert r.message == ""
