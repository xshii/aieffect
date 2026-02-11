"""分层架构新增模块测试：models / exceptions / config / services / pipeline hooks"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from framework.core.config import Config, get_config, init_config
from framework.core.exceptions import (
    AIEffectError,
    CaseNotFoundError,
    ConfigError,
    DependencyError,
    ValidationError,
)
from framework.core.models import Case, SuiteResult, TaskResult
from framework.core.pipeline import PipelineHook, ResultPipeline
from framework.core.reporter import (
    HTMLFormatter,
    JSONFormatter,
    JUnitFormatter,
    ResultFormatter,
    register_formatter,
)

# =========================================================================
# models.py
# =========================================================================


class TestModels:
    def test_defaults_and_basic_fields(self) -> None:
        c = Case(name="foo")
        assert c.timeout == 3600 and c.args == {}

        r = TaskResult(name="tc1", status="passed", duration=1.2)
        assert r.message == ""

    @pytest.mark.parametrize(("failed", "errors", "expected"), [
        (0, 0, True), (1, 0, False), (0, 1, False),
    ])
    def test_suite_result_success(self, failed: int, errors: int, expected: bool) -> None:
        sr = SuiteResult(suite_name="s", failed=failed, errors=errors, total=3, passed=3 - failed - errors)
        assert sr.success is expected

    def test_backward_compat_imports(self) -> None:
        """runner.py 继续导出 Case / SuiteResult"""
        from framework.core.runner import Case as CaseAlias
        from framework.core.runner import SuiteResult as SuiteResultAlias

        assert CaseAlias is Case
        assert SuiteResultAlias is SuiteResult


# =========================================================================
# exceptions.py
# =========================================================================


class TestExceptions:
    @pytest.mark.parametrize("cls", [ConfigError, CaseNotFoundError, DependencyError, ValidationError])
    def test_hierarchy(self, cls: type) -> None:
        assert issubclass(cls, AIEffectError)

    def test_validation_error_details(self) -> None:
        e = ValidationError("校验失败", details=["name", "cmd"])
        assert e.details == ["name", "cmd"] and e.code == "VALIDATION_ERROR"


# =========================================================================
# config.py
# =========================================================================


class TestConfig:
    def test_default_values(self) -> None:
        cfg = Config()
        assert cfg.suite_dir == "testdata/configs"
        assert cfg.max_workers == 8
        assert cfg.storage_backend == "local"

    def test_from_file_missing(self, tmp_path: Path) -> None:
        cfg = Config.from_file(str(tmp_path / "nonexist.yml"))
        assert cfg.suite_dir == "testdata/configs"

    def test_from_file_with_data(self, tmp_path: Path) -> None:
        from framework.utils.yaml_io import save_yaml

        f = tmp_path / "cfg.yml"
        save_yaml(f, {"suite_dir": "/custom/suites", "max_workers": 16})
        cfg = Config.from_file(str(f))
        assert cfg.suite_dir == "/custom/suites"
        assert cfg.max_workers == 16

    def test_extra_fields(self, tmp_path: Path) -> None:
        from framework.utils.yaml_io import save_yaml

        f = tmp_path / "cfg.yml"
        save_yaml(f, {"suite_dir": "s", "custom_field": "hello"})
        cfg = Config.from_file(str(f))
        assert cfg.extra["custom_field"] == "hello"

    def test_to_dict(self) -> None:
        d = Config().to_dict()
        assert isinstance(d, dict) and d["suite_dir"] == "testdata/configs"

    def test_global_singleton(self, tmp_path: Path) -> None:
        import framework.core.config as cfgmod

        cfgmod._current = None
        assert get_config().suite_dir == "testdata/configs"

        from framework.utils.yaml_io import save_yaml

        f = tmp_path / "init.yml"
        save_yaml(f, {"max_workers": 32})
        init_config(str(f))
        assert get_config().max_workers == 32
        cfgmod._current = None


# =========================================================================
# Strategy reporter
# =========================================================================

_SAMPLE_RESULTS = [{"name": "tc1", "status": "passed", "duration": 1.0, "message": "ok"}]
_SAMPLE_SUMMARY = {"total": 1, "passed": 1, "failed": 0, "errors": 0}


class TestStrategyReporter:
    def test_json_formatter(self) -> None:
        f = JSONFormatter()
        assert f.extension() == "json"
        data = json.loads(f.format(_SAMPLE_RESULTS, _SAMPLE_SUMMARY))
        assert data["summary"]["total"] == 1

    def test_html_formatter(self) -> None:
        f = HTMLFormatter()
        assert f.extension() == "html"
        result = f.format(_SAMPLE_RESULTS, _SAMPLE_SUMMARY)
        assert "tc1" in result and "aieffect" in result

    def test_junit_formatter(self) -> None:
        result = JUnitFormatter().format(
            [{"name": "tc1", "status": "failed", "duration": 2.0, "message": "err"}],
            {"total": 1, "passed": 0, "failed": 1, "errors": 0},
        )
        assert "<failure" in result

    def test_register_custom_formatter(self) -> None:
        class CSVFormatter(ResultFormatter):
            def format(self, results: list[dict], summary: dict) -> str:
                return "name,status\n"

            def extension(self) -> str:
                return "csv"

        register_formatter("csv", CSVFormatter)
        from framework.core.reporter import _formatters

        assert "csv" in _formatters


# =========================================================================
# Pipeline Observer hooks
# =========================================================================


class TestPipelineHooks:
    def test_hook_called_on_process(self, tmp_path: Path) -> None:
        captured: list[dict] = []

        class SpyHook(PipelineHook):
            def on_result(self, suite_result: SuiteResult, context: dict) -> None:
                captured.append(context)

        pipeline = ResultPipeline(
            history_file=str(tmp_path / "h.json"),
            result_dir=str(tmp_path / "res"),
        )
        pipeline.subscribe(SpyHook())
        pipeline.process(SuiteResult(suite_name="test", total=1, passed=1), suite="test", environment="sim")

        assert len(captured) == 1
        assert captured[0]["suite"] == "test"

    def test_failing_hook_does_not_block(self, tmp_path: Path) -> None:
        class BadHook(PipelineHook):
            def on_result(self, suite_result: SuiteResult, context: dict) -> None:
                raise RuntimeError("boom")

        pipeline = ResultPipeline(
            history_file=str(tmp_path / "h.json"),
            result_dir=str(tmp_path / "res"),
        )
        pipeline.subscribe(BadHook())
        pipeline.process(SuiteResult(suite_name="test"))  # should not raise


# =========================================================================
# Service layer
# =========================================================================


class TestCaseService:
    @pytest.fixture()
    def svc(self, tmp_path: Path):
        from framework.core.case_manager import CaseManager
        from framework.services.case_service import CaseService

        return CaseService(case_manager=CaseManager(cases_file=str(tmp_path / "cases.yml")))

    def test_create_and_get(self, svc) -> None:
        result = svc.create(name="tc1", cmd="echo hi")
        assert result["name"] == "tc1"
        assert svc.get("tc1")["cmd"] == "echo hi"

    def test_create_validation(self, svc) -> None:
        with pytest.raises(ValidationError, match="必填"):
            svc.create(name="", cmd="")

    def test_delete_not_found(self, svc) -> None:
        with pytest.raises(CaseNotFoundError):
            svc.delete("nonexist")

    def test_list_all(self, svc) -> None:
        svc.create(name="a", cmd="echo a", tags=["smoke"])
        svc.create(name="b", cmd="echo b", tags=["full"])
        assert len(svc.list_all()) == 2
        assert len(svc.list_all(tag="smoke")) == 1


class TestRunService:
    def test_execute(self, tmp_path: Path) -> None:
        import yaml

        from framework.services.run_service import RunRequest, RunService

        suite_dir = tmp_path / "suites"
        suite_dir.mkdir()
        (suite_dir / "test.yml").write_text(yaml.dump({
            "testcases": [{"name": "tc1", "args": {"cmd": "echo ok"}}],
        }))

        cfg = tmp_path / "cfg.yml"
        cfg.write_text(yaml.dump({"suite_dir": str(suite_dir)}))

        pipeline = ResultPipeline(
            history_file=str(tmp_path / "h.json"),
            result_dir=str(tmp_path / "res"),
        )
        svc = RunService(pipeline=pipeline)
        result = svc.execute(RunRequest(suite="test", config_path=str(cfg)))

        assert result.total == 1 and result.passed == 1
