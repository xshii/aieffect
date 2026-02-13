"""shell.py run_cmd 单元测试"""

from __future__ import annotations

import pytest

from framework.core.exceptions import ExecutionError
from framework.utils.shell import run_cmd


class TestRunCmd:
    def test_success(self, tmp_path) -> None:
        r = run_cmd("echo hello", cwd=str(tmp_path), label="test")
        assert r.returncode == 0
        assert "hello" in r.stdout

    def test_failure_raises_runtime_error(self, tmp_path) -> None:
        with pytest.raises(ExecutionError, match="cmd失败"):
            run_cmd("false", cwd=str(tmp_path))

    def test_custom_label_in_error(self, tmp_path) -> None:
        with pytest.raises(ExecutionError, match="mybuild失败"):
            run_cmd("false", cwd=str(tmp_path), label="mybuild")

    def test_env_passed(self, tmp_path) -> None:
        import os
        env = {**os.environ, "MY_TEST_VAR": "42"}
        r = run_cmd("env", cwd=str(tmp_path), env=env, label="env_test")
        assert "MY_TEST_VAR=42" in r.stdout
