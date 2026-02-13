"""调度器仓库准备与 case 过滤测试"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from framework.core.exceptions import ExecutionError, ResourceError, ValidationError
from framework.core.runner import Case, CaseRunner
from framework.core.scheduler import Scheduler, _prepare_repo


def _patch_workspace(monkeypatch: pytest.MonkeyPatch, ws_dir: str) -> None:
    """将 Config.workspace_dir 指向测试临时目录"""
    import framework.core.config as cfgmod
    cfg = cfgmod.get_config()
    monkeypatch.setattr(cfg, "workspace_dir", ws_dir)


class TestPrepareRepo:
    def test_empty_url_returns_none(self) -> None:
        assert _prepare_repo({}) is None
        assert _prepare_repo({"url": ""}) is None

    def test_invalid_ref_raises(self) -> None:
        with pytest.raises(
            (ValueError, ValidationError), match="非法字符",
        ):
            _prepare_repo({"url": "https://example.com/repo.git", "ref": "; rm -rf /"})

    def test_clone_and_cwd(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """模拟 clone 成功后返回正确的 cwd"""
        _patch_workspace(monkeypatch, str(tmp_path / "ws"))

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[0] == "git" and cmd[1] == "clone":
                ws = Path(cmd[-1])
                ws.mkdir(parents=True, exist_ok=True)
                (ws / ".git").mkdir(exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("framework.core.scheduler.subprocess.run", fake_run)

        cwd = _prepare_repo({"url": "https://example.com/myrepo.git", "ref": "v1.0"})
        assert cwd is not None
        assert "myrepo" in str(cwd)

    def test_subpath_not_found(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_workspace(monkeypatch, str(tmp_path / "ws"))

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if cmd[0] == "git" and cmd[1] == "clone":
                ws = Path(cmd[-1])
                ws.mkdir(parents=True, exist_ok=True)
                (ws / ".git").mkdir(exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("framework.core.scheduler.subprocess.run", fake_run)

        with pytest.raises(
            (FileNotFoundError, ResourceError), match="子目录不存在",
        ):
            _prepare_repo({"url": "https://example.com/repo.git", "ref": "main", "path": "nonexist"})

    def test_setup_and_build(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """验证 setup 和 build 命令被调用"""
        _patch_workspace(monkeypatch, str(tmp_path / "ws"))

        call_log: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if isinstance(cmd, list) and cmd[0] == "git" and cmd[1] == "clone":
                ws = Path(cmd[-1])
                ws.mkdir(parents=True, exist_ok=True)
                (ws / ".git").mkdir(exist_ok=True)
            elif isinstance(cmd, list) and cmd[0] != "git":
                call_log.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("framework.core.scheduler.subprocess.run", fake_run)

        _prepare_repo({
            "url": "https://example.com/repo.git",
            "ref": "main",
            "setup": "pip install -r requirements.txt",
            "build": "make build",
        })

        flat = [" ".join(c) for c in call_log]
        assert "pip install -r requirements.txt" in flat
        assert "make build" in flat

    def test_setup_failure_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_workspace(monkeypatch, str(tmp_path / "ws"))

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            if isinstance(cmd, list) and cmd[0] == "git" and cmd[1] == "clone":
                ws = Path(cmd[-1])
                ws.mkdir(parents=True, exist_ok=True)
                (ws / ".git").mkdir(exist_ok=True)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if isinstance(cmd, list) and "install" in cmd:
                return subprocess.CompletedProcess(cmd, 1, "", "error: no such package")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("framework.core.scheduler.subprocess.run", fake_run)

        with pytest.raises((RuntimeError, ExecutionError), match="安装依赖失败"):
            _prepare_repo({
                "url": "https://example.com/repo.git",
                "ref": "main",
                "setup": "pip install nonexist",
            })


    def test_clone_fallback_to_full(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """浅克隆失败时回退到完整克隆"""
        _patch_workspace(monkeypatch, str(tmp_path / "ws"))

        call_log: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            call_log.append(list(cmd))
            if cmd[0] == "git" and cmd[1] == "clone" and "--depth" in cmd:
                # 浅克隆失败
                return subprocess.CompletedProcess(cmd, 128, "", "error: shallow clone")
            if cmd[0] == "git" and cmd[1] == "clone" and "--depth" not in cmd:
                # 完整克隆成功
                ws = Path(cmd[-1])
                ws.mkdir(parents=True, exist_ok=True)
                (ws / ".git").mkdir(exist_ok=True)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("framework.core.scheduler.subprocess.run", fake_run)

        cwd = _prepare_repo({"url": "https://example.com/repo.git", "ref": "main"})
        assert cwd is not None
        # 验证调用了两次 git clone
        clone_cmds = [c for c in call_log if c[0] == "git" and c[1] == "clone"]
        assert len(clone_cmds) == 2
        assert "--depth" in clone_cmds[0]
        assert "--depth" not in clone_cmds[1]

    def test_fetch_existing_repo(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """已存在 .git 目录时执行 fetch+checkout 而非 clone"""
        _patch_workspace(monkeypatch, str(tmp_path / "ws"))

        call_log: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            call_log.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr("framework.core.scheduler.subprocess.run", fake_run)

        # 预创建 .git 目录模拟已克隆仓库
        repo_dir = tmp_path / "ws" / "repo" / "main"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / ".git").mkdir()

        cwd = _prepare_repo({"url": "https://example.com/repo.git", "ref": "main"})
        assert cwd is not None
        # 应执行 fetch + checkout 而非 clone
        git_cmds = [c for c in call_log if c[0] == "git"]
        assert any("fetch" in c for c in git_cmds)
        assert any("checkout" in c for c in git_cmds)
        assert not any("clone" in c for c in git_cmds)


class TestSchedulerWithRepo:
    def test_execute_with_repo_error(self) -> None:
        """repo 准备失败时返回 error 结果"""
        case = Case(
            name="bad_repo",
            args={"cmd": "echo hi"},
            repo={"url": "https://example.com/repo.git", "ref": "; bad"},
        )
        scheduler = Scheduler(max_workers=1)
        results = scheduler.run_all([case])
        assert results[0].status == "error"
        assert "非法字符" in results[0].message


class TestCaseFilter:
    def test_run_suite_case_filter(self, tmp_path: Path) -> None:
        """case_names 过滤只执行指定用例"""
        import yaml

        suite_dir = tmp_path / "suites"
        suite_dir.mkdir()
        suite_file = suite_dir / "test.yml"
        suite_file.write_text(yaml.dump({
            "testcases": [
                {"name": "tc1", "args": {"cmd": "echo one"}},
                {"name": "tc2", "args": {"cmd": "echo two"}},
                {"name": "tc3", "args": {"cmd": "echo three"}},
            ]
        }))

        config_file = tmp_path / "cfg.yml"
        config_file.write_text(yaml.dump({"suite_dir": str(suite_dir)}))

        runner = CaseRunner(config_path=str(config_file), parallel=1)
        result = runner.run_suite("test", case_names=["tc2"])

        assert result.total == 1
        assert result.results[0].name == "tc2"
        assert result.results[0].status == "passed"

    def test_run_suite_no_match(self, tmp_path: Path) -> None:
        import yaml

        suite_dir = tmp_path / "suites"
        suite_dir.mkdir()
        suite_file = suite_dir / "test.yml"
        suite_file.write_text(yaml.dump({
            "testcases": [{"name": "tc1", "args": {"cmd": "echo one"}}]
        }))

        config_file = tmp_path / "cfg.yml"
        config_file.write_text(yaml.dump({"suite_dir": str(suite_dir)}))

        runner = CaseRunner(config_path=str(config_file), parallel=1)
        result = runner.run_suite("test", case_names=["nonexist"])

        assert result.total == 0
