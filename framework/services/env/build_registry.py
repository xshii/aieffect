"""构建环境注册表管理

职责:
- 构建环境的 CRUD 操作
- 数据持久化到 YAML
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.core.registry import YamlRegistry

from framework.core.exceptions import ValidationError
from framework.core.models import BuildEnvSpec, BuildEnvType

logger = logging.getLogger(__name__)


class BuildEnvRegistry:
    """构建环境注册表 - CRUD 操作"""

    def __init__(self, registry: YamlRegistry) -> None:
        self._registry = registry

    def _build_envs(self) -> dict[str, dict[str, Any]]:
        """获取构建环境配置字典"""
        return self._registry._section()

    def register(self, spec: BuildEnvSpec) -> dict[str, Any]:
        """注册构建环境"""
        if not spec.name:
            raise ValidationError("构建环境 name 为必填")
        if spec.build_env_type not in BuildEnvType.__members__.values():
            raise ValidationError(f"不支持的构建环境类型: {spec.build_env_type}")
        entry: dict[str, Any] = {
            "build_env_type": spec.build_env_type,
            "description": spec.description,
            "work_dir": spec.work_dir,
            "variables": spec.variables,
            "host": spec.host, "port": spec.port,
            "user": spec.user, "key_path": spec.key_path,
        }
        self._build_envs()[spec.name] = entry
        self._registry._save()
        logger.info("构建环境已注册: %s (type=%s)", spec.name, spec.build_env_type)
        return entry

    def get(self, name: str) -> BuildEnvSpec | None:
        """获取构建环境规格"""
        entry = self._build_envs().get(name)
        if entry is None:
            return None
        return BuildEnvSpec(
            name=name,
            build_env_type=entry.get("build_env_type", BuildEnvType.LOCAL),
            description=entry.get("description", ""),
            work_dir=entry.get("work_dir", ""),
            variables=entry.get("variables", {}),
            host=entry.get("host", ""),
            port=entry.get("port", 22),
            user=entry.get("user", ""),
            key_path=entry.get("key_path", ""),
        )

    def list(self) -> list[dict[str, Any]]:
        """列出所有构建环境"""
        return [{"name": k, **v} for k, v in self._build_envs().items()]

    def remove(self, name: str) -> bool:
        """删除构建环境"""
        envs = self._build_envs()
        if name not in envs:
            return False
        del envs[name]
        self._registry._save()
        return True
