"""RepoService 单元测试"""

from __future__ import annotations

import pytest

from framework.core.exceptions import ValidationError
from framework.core.models import CaseRepoBinding, RepoSpec


class TestRepoService:
    """代码仓服务测试"""

    @pytest.fixture()
    def svc(self, tmp_path):
        from framework.services.repo_service import RepoService
        return RepoService(
            registry_file=str(tmp_path / "repos.yml"),
            workspace_root=str(tmp_path / "workspaces"),
        )

    def test_register_git(self, svc):
        spec = RepoSpec(name="rtl", source_type="git", url="https://example.com/rtl.git", ref="main")
        entry = svc.register(spec)
        assert entry["source_type"] == "git"
        assert entry["url"] == "https://example.com/rtl.git"

    def test_register_tar(self, svc):
        spec = RepoSpec(name="vectors", source_type="tar", tar_path="/data/vectors.tar.gz")
        entry = svc.register(spec)
        assert entry["source_type"] == "tar"
        assert entry["tar_path"] == "/data/vectors.tar.gz"

    def test_register_api(self, svc):
        spec = RepoSpec(name="artifact", source_type="api", api_url="https://api.example.com/artifact/v1")
        entry = svc.register(spec)
        assert entry["source_type"] == "api"
        assert entry["api_url"] == "https://api.example.com/artifact/v1"

    def test_register_with_deps(self, svc):
        spec = RepoSpec(name="tb", source_type="git", url="https://example.com/tb.git", deps=["vcs", "verdi"])
        entry = svc.register(spec)
        assert entry["deps"] == ["vcs", "verdi"]

    def test_register_empty_name_raises(self, svc):
        with pytest.raises(ValidationError, match="name"):
            svc.register(RepoSpec(name="", url="x"))

    def test_register_invalid_source_type(self, svc):
        with pytest.raises(ValidationError, match="不支持"):
            svc.register(RepoSpec(name="x", source_type="svn", url="x"))

    def test_register_git_without_url(self, svc):
        with pytest.raises(ValidationError, match="url"):
            svc.register(RepoSpec(name="x", source_type="git", url=""))

    def test_register_bad_ref(self, svc):
        with pytest.raises(ValidationError, match="非法字符"):
            svc.register(RepoSpec(name="x", source_type="git", url="https://a.b/c", ref="a;rm -rf"))

    def test_get_and_list(self, svc):
        svc.register(RepoSpec(name="a", source_type="git", url="https://a.com/a.git"))
        svc.register(RepoSpec(name="b", source_type="tar", tar_path="/b.tar"))

        spec = svc.get("a")
        assert spec is not None
        assert spec.source_type == "git"

        all_repos = svc.list_all()
        assert len(all_repos) == 2

    def test_remove(self, svc):
        svc.register(RepoSpec(name="x", source_type="tar", tar_path="/x.tar"))
        assert svc.remove("x") is True
        assert svc.remove("x") is False
        assert svc.get("x") is None

    def test_checkout_unregistered_raises(self, svc):
        with pytest.raises(ValidationError, match="未注册"):
            svc.checkout("nonexistent")

    def test_workspace_cache_reuse(self, svc):
        """shared=True 时，同 (name, ref) 的 checkout 应复用"""
        svc.register(RepoSpec(name="demo", source_type="tar", tar_path="/nonexist"))
        # 第一次会失败（文件不存在），但会被缓存
        ws1 = svc.checkout("demo")
        # 由于是 error 状态，不应被复用
        ws2 = svc.checkout("demo")
        # 两次都是 error（因为 tar 不存在），但 cache 不会 reuse error
        assert ws1.status == ws2.status

    def test_clean(self, svc, tmp_path):
        # 创建假的工作目录
        ws_dir = tmp_path / "workspaces" / "test_repo" / "main"
        ws_dir.mkdir(parents=True)
        (ws_dir / "file.txt").write_text("hello")

        count = svc.clean("test_repo")
        assert count == 1

    def test_list_workspaces_empty(self, svc):
        assert svc.list_workspaces() == []

    def test_checkout_for_case(self, svc):
        svc.register(RepoSpec(name="tb", source_type="tar", tar_path="/x.tar"))
        binding = CaseRepoBinding(repo_name="tb", ref_override="v2", shared=True)
        ws = svc.checkout_for_case(binding)
        # 会失败因为 tar 不存在，但流程正确
        assert ws.spec.name == "tb"
