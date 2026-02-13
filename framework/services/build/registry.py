"""构建配置注册与管理

职责:
- 构建配置 CRUD 操作
- BuildSpec 序列化/反序列化
- 配置持久化
"""

from __future__ import annotations

import logging
from typing import Any

from framework.core.exceptions import ValidationError
from framework.core.models import BuildSpec
from framework.core.registry import YamlRegistry

logger = logging.getLogger(__name__)


class BuildRegistry(YamlRegistry):
    """构建配置注册表"""

    section_key = "builds"

    def register(self, spec: BuildSpec) -> dict[str, str]:
        """注册构建配置"""
        if not spec.name:
            raise ValidationError("构建 name 为必填")
        entry: dict[str, str] = {
            "repo_name": spec.repo_name,
            "setup_cmd": spec.setup_cmd,
            "build_cmd": spec.build_cmd,
            "clean_cmd": spec.clean_cmd,
            "output_dir": spec.output_dir,
        }
        self._put(spec.name, entry)
        logger.info("构建配置已注册: %s", spec.name)
        return entry

    def get(self, name: str) -> BuildSpec | None:
        """获取已注册构建定义"""
        entry = self._get_raw(name)
        if entry is None:
            return None
        return BuildSpec(
            name=name,
            repo_name=entry.get("repo_name", ""),
            setup_cmd=entry.get("setup_cmd", ""),
            build_cmd=entry.get("build_cmd", ""),
            clean_cmd=entry.get("clean_cmd", ""),
            output_dir=entry.get("output_dir", ""),
        )

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有构建配置"""
        return self._list_raw()

    def remove(self, name: str) -> bool:
        """删除构建配置"""
        if not self._remove(name):
            return False
        logger.info("构建配置已移除: %s", name)
        return True
