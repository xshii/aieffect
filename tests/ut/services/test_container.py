"""ServiceContainer 单元测试"""

from __future__ import annotations

from pathlib import Path

import pytest

import framework.core.config as cfgmod
from framework.services.container import (
    ServiceContainer,
    get_container,
    reset_container,
)


@pytest.fixture(autouse=True)
def _setup_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """确保测试有独立的配置和数据目录"""
    cfg = cfgmod.Config(
        workspace_dir=str(tmp_path / "ws"),
        result_dir=str(tmp_path / "results"),
        history_file=str(tmp_path / "history.json"),
        cases_file=str(tmp_path / "cases.yml"),
    )
    monkeypatch.setattr(cfgmod, "_current", cfg)
    reset_container()
    yield
    reset_container()


class TestServiceContainer:
    def test_lazy_loading(self) -> None:
        c = ServiceContainer()
        assert len(c._instances) == 0
        _ = c.repo
        assert "repo" in c._instances

    def test_shared_instances(self) -> None:
        c = ServiceContainer()
        r1 = c.repo
        r2 = c.repo
        assert r1 is r2

    def test_build_gets_repo_service(self) -> None:
        c = ServiceContainer()
        build_svc = c.build
        assert build_svc._repo_service is c.repo

    def test_stimulus_gets_repo_service(self) -> None:
        c = ServiceContainer()
        stim_svc = c.stimulus
        assert stim_svc._repo_service is c.repo

    def test_all_services_accessible(self) -> None:
        c = ServiceContainer()
        assert c.repo is not None
        assert c.build is not None
        assert c.stimulus is not None
        assert c.env is not None
        assert c.result is not None
        assert c.run is not None


class TestGetContainer:
    def test_singleton(self) -> None:
        c1 = get_container()
        c2 = get_container()
        assert c1 is c2

    def test_reset(self) -> None:
        c1 = get_container()
        reset_container()
        c2 = get_container()
        assert c1 is not c2
