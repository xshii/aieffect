"""依赖包注册表管理

职责:
- 从 YAML 清单文件加载包定义
- 支持 eda_tools 和 packages 两个配置段
"""

from __future__ import annotations

import logging
from pathlib import Path

from framework.core.dep.models import PackageInfo
from framework.utils.yaml_io import load_yaml

logger = logging.getLogger(__name__)


class PackageRegistry:
    """依赖包注册表 - 从清单文件加载包定义"""

    def __init__(self, registry_path: Path) -> None:
        self.registry_path = registry_path

    def load(self) -> dict[str, PackageInfo]:
        """从清单文件加载所有包定义"""
        if not self.registry_path.exists():
            logger.warning("清单文件不存在: %s", self.registry_path)
            return {}

        data = load_yaml(self.registry_path)
        packages: dict[str, PackageInfo] = {}

        # 加载 eda_tools 段 —— 统一作为 local 类型的包
        for name, info in (data.get("eda_tools") or {}).items():
            if info is None:
                continue
            install_path = info.get("install_path", "")
            packages[name] = PackageInfo(
                name=name,
                owner=info.get("owner", "eda"),
                version=info.get("version", "latest"),
                source="local",
                description=info.get("description", f"EDA 工具 {name}"),
                base_path=install_path,
                env_vars=info.get("env_vars", {}),
            )

        # 加载 packages 段
        for name, info in (data.get("packages") or {}).items():
            if info is None:
                continue
            packages[name] = PackageInfo(
                name=name,
                owner=info.get("owner", "unknown"),
                version=info.get("version", "latest"),
                source=info.get("source", "api"),
                description=info.get("description", ""),
                base_path=info.get("base_path", ""),
                api_url=info.get("api_url", ""),
                url=info.get("url", ""),
                lfs_path=info.get("lfs_path", ""),
                checksum_sha256=info.get("checksum_sha256", ""),
                env_vars=info.get("env_vars", {}),
            )

        logger.info("已加载 %d 个依赖包", len(packages))
        return packages

    @staticmethod
    def list_packages(packages: dict[str, PackageInfo]) -> list[dict[str, str]]:
        """格式化包列表用于查询"""
        results = []
        for p in packages.values():
            info: dict[str, str] = {
                "name": p.name,
                "owner": p.owner,
                "version": p.version,
                "source": p.source,
                "description": p.description,
            }
            if p.base_path:
                info["base_path"] = p.base_path
            results.append(info)
        return results
