"""依赖包管理器测试 - 本地版本切换 + 远程回退"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from framework.core.dep_manager import DepManager


def _write_manifest(tmp_path: Path, data: dict) -> Path:
    manifest = tmp_path / "manifest.yml"
    manifest.write_text(yaml.dump(data, allow_unicode=True))
    return manifest


class TestLocalVersionSwitch:
    """本地版本切换（核心功能）"""

    @pytest.mark.parametrize("version_exists", [True, False])
    def test_resolve_local_version(self, tmp_path: Path, version_exists: bool) -> None:
        """本地版本存在时返回路径，不存在时返回 None"""
        base = tmp_path / "vcs"
        if version_exists:
            (base / "U-2023.03-SP2").mkdir(parents=True)
        else:
            base.mkdir()

        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {
                    "version": "U-2023.03-SP2",
                    "install_path": str(base),
                },
            },
        })

        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        path = dm.resolve("vcs")
        if version_exists:
            assert path == base / "U-2023.03-SP2"
        else:
            assert path is None

    def test_resolve_with_explicit_version(self, tmp_path: Path) -> None:
        """指定版本切换"""
        base = tmp_path / "vcs"
        (base / "U-2023.03-SP2").mkdir(parents=True)
        (base / "U-2024.06").mkdir(parents=True)

        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {
                    "version": "U-2023.03-SP2",
                    "install_path": str(base),
                },
            },
        })

        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        # 切换到另一个版本
        path = dm.resolve("vcs", version="U-2024.06")
        assert path is not None
        assert "U-2024.06" in str(path)

    def test_resolve_unknown_package_raises(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, {"eda_tools": {}})
        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        with pytest.raises(ValueError, match="不在清单中"):
            dm.resolve("nonexist")

    def test_fetch_local_exists_no_download(self, tmp_path: Path) -> None:
        """本地版本存在时 fetch 不触发下载，直接返回"""
        base = tmp_path / "vcs"
        ver_dir = base / "U-2023.03-SP2"
        ver_dir.mkdir(parents=True)
        (ver_dir / "bin").mkdir()

        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {
                    "version": "U-2023.03-SP2",
                    "install_path": str(base),
                },
            },
        })

        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        path = dm.fetch("vcs")
        assert path == ver_dir

    def test_fetch_local_not_exists_raises(self, tmp_path: Path) -> None:
        """纯 local 包版本不存在时 fetch 报错"""
        base = tmp_path / "vcs"
        base.mkdir()

        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {
                    "version": "U-2099.99",
                    "install_path": str(base),
                },
            },
        })

        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        with pytest.raises(FileNotFoundError, match="本地包.*不存在"):
            dm.fetch("vcs")


class TestListLocalVersions:
    def test_list_versions_eda(self, tmp_path: Path) -> None:
        """列出 EDA 工具本地已安装版本"""
        base = tmp_path / "vcs"
        (base / "U-2022.06").mkdir(parents=True)
        (base / "U-2023.03-SP2").mkdir(parents=True)
        (base / "U-2024.06").mkdir(parents=True)
        (base / ".hidden").mkdir(parents=True)  # 隐藏目录应被忽略

        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {
                    "version": "U-2023.03-SP2",
                    "install_path": str(base),
                },
            },
        })

        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        versions = dm.list_local_versions("vcs")
        assert versions == ["U-2022.06", "U-2023.03-SP2", "U-2024.06"]

    def test_list_versions_empty(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {
                    "version": "1.0",
                    "install_path": str(tmp_path / "nonexist"),
                },
            },
        })
        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        assert dm.list_local_versions("vcs") == []

    def test_list_versions_api_package(self, tmp_path: Path) -> None:
        """api 类型包也支持 base_path 本地版本列表"""
        base = tmp_path / "model_lib"
        (base / "v1.0").mkdir(parents=True)
        (base / "v2.0").mkdir(parents=True)

        manifest = _write_manifest(tmp_path, {
            "packages": {
                "model_lib": {
                    "owner": "ml-team",
                    "version": "v2.0",
                    "source": "api",
                    "base_path": str(base),
                    "api_url": "https://example.com/api",
                },
            },
        })

        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        versions = dm.list_local_versions("model_lib")
        assert "v1.0" in versions
        assert "v2.0" in versions


class TestFetchWithFallback:
    """本地不存在时回退远程拉取"""

    def test_api_package_local_first(self, tmp_path: Path) -> None:
        """api 包配了 base_path，本地版本存在时直接用"""
        base = tmp_path / "firmware"
        ver_dir = base / "v1.3.2"
        ver_dir.mkdir(parents=True)
        (ver_dir / "firmware.bin").write_bytes(b"data")

        manifest = _write_manifest(tmp_path, {
            "packages": {
                "firmware": {
                    "owner": "fw-team",
                    "version": "v1.3.2",
                    "source": "api",
                    "base_path": str(base),
                    "api_url": "https://example.com/api",
                },
            },
        })

        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        path = dm.fetch("firmware")
        assert path == ver_dir  # 本地命中，不下载


class TestEdaToolsLoading:
    def test_eda_tools_loaded_as_local(self, tmp_path: Path) -> None:
        """eda_tools 段自动作为 local source 加载"""
        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {"version": "1.0", "install_path": "/opt/vcs"},
                "verdi": {"version": "2.0", "install_path": "/opt/verdi"},
            },
        })
        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        assert "vcs" in dm.packages
        assert dm.packages["vcs"].source == "local"
        assert dm.packages["vcs"].base_path == "/opt/vcs"
        assert "verdi" in dm.packages

    def test_both_eda_and_packages_loaded(self, tmp_path: Path) -> None:
        """eda_tools 和 packages 同时加载"""
        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {"version": "1.0", "install_path": "/opt/vcs"},
            },
            "packages": {
                "model_lib": {
                    "owner": "ml-team",
                    "version": "v1.0",
                    "source": "api",
                    "api_url": "https://example.com",
                },
            },
        })
        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        assert len(dm.packages) == 2
        assert dm.packages["vcs"].source == "local"
        assert dm.packages["model_lib"].source == "api"


class TestEnvVars:
    def test_get_env_vars_with_path(self, tmp_path: Path) -> None:
        base = tmp_path / "vcs"
        ver_dir = base / "U-2023.03-SP2"
        ver_dir.mkdir(parents=True)

        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {
                    "version": "U-2023.03-SP2",
                    "install_path": str(base),
                    "env_vars": {
                        "VCS_HOME": "{path}",
                        "PATH": "{path}/bin:$PATH",
                    },
                },
            },
        })
        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        env = dm.get_env_vars("vcs")
        assert env["VCS_HOME"] == str(ver_dir)
        assert env["PATH"] == f"{ver_dir}/bin:$PATH"

    def test_get_env_vars_unknown(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, {"eda_tools": {}})
        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        assert dm.get_env_vars("nonexist") == {}


class TestListPackages:
    def test_includes_base_path(self, tmp_path: Path) -> None:
        manifest = _write_manifest(tmp_path, {
            "eda_tools": {
                "vcs": {"version": "1.0", "install_path": "/opt/vcs"},
            },
        })
        dm = DepManager(registry_path=str(manifest), cache_dir=str(tmp_path / "cache"))
        pkgs = dm.list_packages()
        assert len(pkgs) == 1
        assert pkgs[0]["base_path"] == "/opt/vcs"
        assert pkgs[0]["source"] == "local"
