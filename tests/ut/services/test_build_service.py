"""BuildService 单元测试"""

from __future__ import annotations

import pytest

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import BuildSpec


class TestBuildService:
    """构建服务测试"""

    @pytest.fixture()
    def svc(self, tmp_path):
        from framework.services.build_service import BuildService
        return BuildService(
            registry_file=str(tmp_path / "builds.yml"),
            output_root=str(tmp_path / "outputs"),
        )

    def test_register_and_get(self, svc):
        spec = BuildSpec(
            name="rtl_build", repo_name="rtl",
            build_cmd="make compile", clean_cmd="make clean",
            output_dir="output",
        )
        svc.register(spec)
        got = svc.get("rtl_build")
        assert got is not None
        assert got.build_cmd == "make compile"
        assert got.output_dir == "output"

    def test_register_empty_name_raises(self, svc):
        with pytest.raises(ValidationError, match="name"):
            svc.register(BuildSpec(name=""))

    def test_list_all(self, svc):
        svc.register(BuildSpec(name="a", build_cmd="make a"))
        svc.register(BuildSpec(name="b", build_cmd="make b"))
        assert len(svc.list_all()) == 2

    def test_remove(self, svc):
        svc.register(BuildSpec(name="tmp"))
        assert svc.remove("tmp") is True
        assert svc.remove("tmp") is False

    def test_build_nonexistent_raises(self, svc):
        with pytest.raises(CaseNotFoundError, match="不存在"):
            svc.build("no_such")

    def test_build_success(self, svc, tmp_path):
        work = tmp_path / "build_work"
        work.mkdir()
        svc.register(BuildSpec(name="echo_build", build_cmd="echo done"))
        result = svc.build("echo_build", work_dir=str(work))
        assert result.status == "success"
        assert result.duration > 0

    def test_build_failure(self, svc, tmp_path):
        work = tmp_path / "fail_work"
        work.mkdir()
        svc.register(BuildSpec(name="fail_build", build_cmd="false"))
        result = svc.build("fail_build", work_dir=str(work))
        assert result.status == "failed"
        assert "失败" in result.message

    def test_build_with_setup(self, svc, tmp_path):
        work = tmp_path / "setup_work"
        work.mkdir()
        svc.register(BuildSpec(
            name="setup_build", setup_cmd="echo setup", build_cmd="echo build",
        ))
        result = svc.build("setup_build", work_dir=str(work))
        assert result.status == "success"

    def test_clean_no_cmd(self, svc):
        svc.register(BuildSpec(name="no_clean"))
        assert svc.clean("no_clean") is True

    def test_clean_nonexistent(self, svc):
        assert svc.clean("no_such") is False

    # ---- 构建缓存 ----

    def test_build_cache_hit(self, svc, tmp_path):
        """同名同分支第二次构建应命中缓存"""
        work = tmp_path / "cache_work"
        work.mkdir()
        svc.register(BuildSpec(name="cache_build", build_cmd="echo done"))
        r1 = svc.build("cache_build", work_dir=str(work), repo_ref="main")
        assert r1.status == "success"
        assert r1.cached is False

        r2 = svc.build("cache_build", work_dir=str(work), repo_ref="main")
        assert r2.status == "cached"
        assert r2.cached is True

    def test_build_cache_miss_new_branch(self, svc, tmp_path):
        """指定新分支应触发重新构建"""
        work = tmp_path / "branch_work"
        work.mkdir()
        svc.register(BuildSpec(name="branch_build", build_cmd="echo done"))
        r1 = svc.build("branch_build", work_dir=str(work), repo_ref="main")
        assert r1.status == "success"
        assert r1.cached is False

        r2 = svc.build("branch_build", work_dir=str(work), repo_ref="develop")
        assert r2.status == "success"
        assert r2.cached is False

    def test_build_force_rebuild(self, svc, tmp_path):
        """force=True 应强制重建"""
        work = tmp_path / "force_work"
        work.mkdir()
        svc.register(BuildSpec(name="force_build", build_cmd="echo done"))
        svc.build("force_build", work_dir=str(work), repo_ref="main")
        r = svc.build("force_build", work_dir=str(work), repo_ref="main", force=True)
        assert r.status == "success"
        assert r.cached is False

    def test_is_cached(self, svc, tmp_path):
        work = tmp_path / "is_cache_work"
        work.mkdir()
        svc.register(BuildSpec(name="chk", build_cmd="echo done"))
        assert svc.is_cached("chk", "v1") is False
        svc.build("chk", work_dir=str(work), repo_ref="v1")
        assert svc.is_cached("chk", "v1") is True
        assert svc.is_cached("chk", "v2") is False

    def test_invalidate_cache(self, svc, tmp_path):
        work = tmp_path / "inv_work"
        work.mkdir()
        svc.register(BuildSpec(name="inv", build_cmd="echo done"))
        svc.build("inv", work_dir=str(work), repo_ref="main")
        assert svc.is_cached("inv", "main") is True
        svc.invalidate_cache("inv", "main")
        assert svc.is_cached("inv", "main") is False
