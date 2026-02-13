"""依赖包本地解析器

职责:
- 解析本地已安装版本的路径（不触发下载）
- 列出本地已安装的版本
- 展开环境变量模板
"""

from __future__ import annotations

import logging
from pathlib import Path

from framework.core.dep.models import DEFAULT_PACKAGES_DIR, PackageInfo

logger = logging.getLogger(__name__)


class PackageResolver:
    """依赖包本地解析器 - 仅做本地查找，不触发下载"""

    def __init__(
        self,
        packages: dict[str, PackageInfo],
        cache_dir: Path,
    ) -> None:
        self.packages = packages
        self.cache_dir = cache_dir

    def resolve(self, name: str, version: str | None = None) -> Path | None:
        """解析本地已安装版本的路径，不触发任何下载。

        返回版本目录路径，若本地不存在则返回 None。
        """
        pkg = self.packages.get(name)
        if pkg is None:
            raise ValueError(
                f"依赖包 '{name}' 不在清单中。"
                f"可用: {list(self.packages.keys())}"
            )

        ver = version or pkg.version
        local_path = self.local_version_path(pkg, ver)
        if local_path and local_path.exists():
            logger.info("本地命中: %s@%s -> %s", name, ver, local_path)
            return local_path
        return None

    def local_version_path(self, pkg: PackageInfo, version: str) -> Path | None:
        """计算包在本地的版本目录路径。

        路径规则:
          - 有 base_path: base_path/version/  （如 /opt/synopsys/vcs/U-2023.03-SP2/）
          - 无 base_path 但 source=lfs: deps/packages/<name>/<version>/
          - 其他: deps/cache/<name>/<version>/
        """
        if pkg.base_path:
            return Path(pkg.base_path) / version
        if pkg.source == "lfs":
            if pkg.lfs_path:
                return Path(pkg.lfs_path)
            return Path(DEFAULT_PACKAGES_DIR) / pkg.name / version
        # api/url 类型的缓存目录
        return self.cache_dir / pkg.name / version

    def list_local_versions(self, name: str) -> list[str]:
        """列出某个包在本地已安装的所有版本。

        基于 base_path 目录扫描子目录，每个子目录名视为一个版本。
        """
        pkg = self.packages.get(name)
        if pkg is None:
            raise ValueError(
                f"依赖包 '{name}' 不在清单中。"
                f"可用: {list(self.packages.keys())}"
            )

        if pkg.base_path:
            base = Path(pkg.base_path)
        elif pkg.source == "lfs":
            base = Path(DEFAULT_PACKAGES_DIR) / pkg.name
        else:
            base = self.cache_dir / pkg.name

        if not base.exists():
            return []

        return sorted(
            d.name for d in base.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    def get_env_vars(self, name: str, version: str | None = None) -> dict[str, str]:
        """获取包的环境变量，版本占位符 {version} 和 {path} 会被替换。"""
        pkg = self.packages.get(name)
        if pkg is None:
            return {}
        ver = version or pkg.version
        local_path = self.local_version_path(pkg, ver)
        result: dict[str, str] = {}
        for k, v in pkg.env_vars.items():
            val = v.replace("{version}", ver)
            if local_path:
                val = val.replace("{path}", str(local_path))
            result[k] = val
        return result
