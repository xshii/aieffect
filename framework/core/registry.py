"""YAML 注册表基类 — 消除 5 处重复的 load/save/CRUD 模式

所有基于 YAML 文件的注册表（cases, repos, builds, stimuli, envs）
共享相同的加载、保存、字段访问、增删改查逻辑。

子类只需指定 section_key，即可继承完整 CRUD。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from framework.utils.yaml_io import load_yaml, save_yaml

logger = logging.getLogger(__name__)


class YamlRegistry:
    """YAML 文件注册表基类

    子类用法:
        class MyRegistry(YamlRegistry):
            section_key = "items"
    """

    section_key: str = "entries"

    def __init__(self, registry_file: str) -> None:
        self.registry_file = Path(registry_file)
        self._data: dict[str, Any] = load_yaml(self.registry_file)

    @staticmethod
    def _resolve_registry_file(registry_file: str, config_key: str) -> str:
        """从 Config 解析注册表文件路径（消除各子类的重复 getattr 模式）"""
        if registry_file:
            return registry_file
        from framework.core.config import get_config
        return str(getattr(get_config(), config_key))

    def _section(self) -> dict[str, dict[str, Any]]:
        """获取当前 section 字典（自动创建）"""
        result: dict[str, dict[str, Any]] = self._data.setdefault(self.section_key, {})
        return result

    def _save(self) -> None:
        """持久化到 YAML 文件"""
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.registry_file, self._data)

    def _put(self, name: str, entry: dict[str, Any]) -> dict[str, Any]:
        """写入条目并保存"""
        self._section()[name] = entry
        self._save()
        return entry

    def _get_raw(self, name: str) -> dict[str, Any] | None:
        """获取原始字典"""
        return self._section().get(name)

    def _list_raw(self) -> list[dict[str, Any]]:
        """列出所有条目（带 name 字段）"""
        return [{"name": k, **v} for k, v in self._section().items()]

    def _remove(self, name: str) -> bool:
        """删除条目"""
        section = self._section()
        if name not in section:
            return False
        del section[name]
        self._save()
        return True
