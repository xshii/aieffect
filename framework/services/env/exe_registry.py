"""执行环境注册表管理

职责:
- 执行环境的 CRUD 操作
- 数据持久化到 YAML
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.core.registry import YamlRegistry

from framework.core.exceptions import ValidationError
from framework.core.models import ExeEnvSpec, ExeEnvType, ToolSpec

logger = logging.getLogger(__name__)


class ExeEnvRegistry:
    """执行环境注册表 - CRUD 操作"""

    def __init__(self, registry: YamlRegistry) -> None:
        self._registry = registry

    def _exe_envs(self) -> dict[str, dict[str, Any]]:
        """获取执行环境配置字典"""
        result: dict[str, dict[str, Any]] = self._registry._data.setdefault("exe_envs", {})
        return result

    def register(self, spec: ExeEnvSpec) -> dict[str, Any]:
        """注册执行环境"""
        if not spec.name:
            raise ValidationError("执行环境 name 为必填")
        if spec.exe_env_type not in ExeEnvType.__members__.values():
            raise ValidationError(f"不支持的执行环境类型: {spec.exe_env_type}")
        tools_dict: dict[str, dict[str, Any]] = {}
        for tname, tool in spec.tools.items():
            tools_dict[tname] = {
                "version": tool.version,
                "install_path": tool.install_path,
                "env_vars": tool.env_vars,
            }
        entry: dict[str, Any] = {
            "exe_env_type": spec.exe_env_type,
            "description": spec.description,
            "api_url": spec.api_url, "api_token": spec.api_token,
            "variables": spec.variables, "tools": tools_dict,
            "licenses": spec.licenses, "timeout": spec.timeout,
            "build_env_name": spec.build_env_name,
        }
        self._exe_envs()[spec.name] = entry
        self._registry._save()
        logger.info("执行环境已注册: %s (type=%s)", spec.name, spec.exe_env_type)
        return entry

    def get(self, name: str) -> ExeEnvSpec | None:
        """获取执行环境规格"""
        entry = self._exe_envs().get(name)
        if entry is None:
            return None
        tools: dict[str, ToolSpec] = {}
        for tname, tinfo in (entry.get("tools") or {}).items():
            ti = tinfo if isinstance(tinfo, dict) else {}
            tools[tname] = ToolSpec(
                name=tname, version=ti.get("version", ""),
                install_path=ti.get("install_path", ""),
                env_vars=ti.get("env_vars", {}),
            )
        return ExeEnvSpec(
            name=name,
            exe_env_type=entry.get("exe_env_type", ExeEnvType.EDA),
            description=entry.get("description", ""),
            api_url=entry.get("api_url", ""),
            api_token=entry.get("api_token", ""),
            variables=entry.get("variables", {}),
            tools=tools,
            licenses=entry.get("licenses", {}),
            timeout=entry.get("timeout", 3600),
            build_env_name=entry.get("build_env_name", ""),
        )

    def list(self) -> list[dict[str, Any]]:
        """列出所有执行环境"""
        return [{"name": k, **v} for k, v in self._exe_envs().items()]

    def remove(self, name: str) -> bool:
        """删除执行环境"""
        envs = self._exe_envs()
        if name not in envs:
            return False
        del envs[name]
        self._registry._save()
        return True
