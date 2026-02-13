"""依赖包管理器 - 门面类（向后兼容）

职责：
- 保持向后兼容性
- 代理到新的模块化实现

重构说明：
- 原 405 行单体类拆分为 4 个模块
- models: 数据模型
- registry: 注册表加载
- resolver: 本地解析
- fetcher: 远程拉取

用法:
    from framework.core.dep_manager import DepManager

    dm = DepManager()
    dm.fetch_all()
    dm.fetch("model_lib", version="v2.1.0")

    # 仅本地切换版本（不下载）
    path = dm.resolve("vcs", version="U-2023.03-SP2")

    # 查看本地已安装版本
    versions = dm.list_local_versions("vcs")
"""

from __future__ import annotations

from pathlib import Path

# 导出数据模型（保持向后兼容）
from framework.core.dep.models import PackageInfo

# 导入子模块
from framework.core.dep.fetcher import PackageFetcher
from framework.core.dep.registry import PackageRegistry
from framework.core.dep.resolver import PackageResolver

__all__ = [
    "PackageInfo",
    "DepManager",
]


class DepManager:
    """依赖包统一管理器（向后兼容门面类）

    优先使用本地已安装版本（base_path/version/），
    仅当本地不存在时才按 source 类型执行远程拉取。
    """

    def __init__(
        self,
        registry_path: str = "",
        cache_dir: str = "",
    ) -> None:
        if not registry_path or not cache_dir:
            from framework.core.config import get_config
            cfg = get_config()
            registry_path = registry_path or cfg.manifest
            cache_dir = cache_dir or cfg.cache_dir

        registry_path_obj = Path(registry_path)
        cache_dir_obj = Path(cache_dir)
        cache_dir_obj.mkdir(parents=True, exist_ok=True)

        # 组合各子模块
        self._registry = PackageRegistry(registry_path_obj)
        self.packages = self._registry.load()

        self._resolver = PackageResolver(self.packages, cache_dir_obj)
        self._fetcher = PackageFetcher(self.packages, cache_dir_obj, self._resolver)

    # ------------------------------------------------------------------
    # 本地版本解析（不下载）
    # ------------------------------------------------------------------

    def resolve(self, name: str, version: str | None = None) -> Path | None:
        """解析本地已安装版本的路径，不触发任何下载。

        返回版本目录路径，若本地不存在则返回 None。
        """
        return self._resolver.resolve(name, version)

    def list_local_versions(self, name: str) -> list[str]:
        """列出某个包在本地已安装的所有版本。

        基于 base_path 目录扫描子目录，每个子目录名视为一个版本。
        """
        return self._resolver.list_local_versions(name)

    # ------------------------------------------------------------------
    # 拉取（本地优先 + 远程回退）
    # ------------------------------------------------------------------

    def fetch(self, name: str, version: str | None = None) -> Path:
        """拉取单个依赖包，返回本地路径。

        策略: 本地优先
          1. 检查本地是否已存在该版本 → 直接返回
          2. 不存在则按 source 类型远程拉取
        """
        return self._fetcher.fetch(name, version)

    def fetch_all(self) -> dict[str, Path | str]:
        """拉取清单中的全部包，返回 {name: path|error_msg}"""
        return self._fetcher.fetch_all()

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_packages(self) -> list[dict[str, str]]:
        return PackageRegistry.list_packages(self.packages)

    def get_env_vars(self, name: str, version: str | None = None) -> dict[str, str]:
        """获取包的环境变量，版本占位符 {version} 和 {path} 会被替换。"""
        return self._resolver.get_env_vars(name, version)

    # ------------------------------------------------------------------
    # LFS 上传
    # ------------------------------------------------------------------

    def upload_lfs(self, name: str, version: str, src_path: str) -> Path:
        """上传包到 Git LFS 存储"""
        return self._fetcher.upload_lfs(name, version, src_path)
