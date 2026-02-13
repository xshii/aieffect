"""环境服务 - 门面类（向后兼容）

职责：
- 保持向后兼容性
- 代理到新的模块化实现

重构说明：
- 原 509 行单体类拆分为 5 个模块
- handlers: 环境处理器 (Strategy Pattern)
- build_registry: 构建环境 CRUD
- exe_registry: 执行环境 CRUD
- lifecycle: 生命周期管理
- executor: 命令执行

环境分为两大类:
  构建环境 (BuildEnv): local（本地）/ remote（远端服务器）
  执行环境 (ExeEnv):   eda / fpga / silicon（均为 Web API）/ same_as_build

公共生命周期: apply → (timeout | release | invalid)

编排顺序: 环境优先于代码仓（环境决定代码仓检出位置）
"""

from __future__ import annotations

from typing import Any

from framework.core.models import (
    BuildEnvSpec,
    EnvSession,
    ExeEnvSpec,
)
from framework.core.registry import YamlRegistry
from framework.services.env.build_registry import BuildEnvRegistry
from framework.services.env.exe_registry import ExeEnvRegistry
from framework.services.env.executor import EnvExecutor
from framework.services.env.lifecycle import EnvLifecycle

__all__ = [
    "EnvService",
]


class EnvService(YamlRegistry):
    """环境全生命周期管理（向后兼容门面类）"""

    section_key = "build_envs"

    def __init__(self, registry_file: str = "") -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "envs_file", "data/environments.yml")
        super().__init__(registry_file)

        # 组合各子模块
        self._build_registry = BuildEnvRegistry(self)
        self._exe_registry = ExeEnvRegistry(self)
        self._lifecycle = EnvLifecycle(self._build_registry, self._exe_registry)
        self._executor = EnvExecutor(self._lifecycle)

    # ---- 构建环境 CRUD ----

    def register_build_env(self, spec: BuildEnvSpec) -> dict[str, Any]:
        """注册构建环境"""
        return self._build_registry.register(spec)

    def get_build_env(self, name: str) -> BuildEnvSpec | None:
        """获取构建环境规格"""
        return self._build_registry.get(name)

    def list_build_envs(self) -> list[dict[str, Any]]:
        """列出所有构建环境"""
        return self._build_registry.list()

    def remove_build_env(self, name: str) -> bool:
        """删除构建环境"""
        return self._build_registry.remove(name)

    # ---- 执行环境 CRUD ----

    def register_exe_env(self, spec: ExeEnvSpec) -> dict[str, Any]:
        """注册执行环境"""
        return self._exe_registry.register(spec)

    def get_exe_env(self, name: str) -> ExeEnvSpec | None:
        """获取执行环境规格"""
        return self._exe_registry.get(name)

    def list_exe_envs(self) -> list[dict[str, Any]]:
        """列出所有执行环境"""
        return self._exe_registry.list()

    def remove_exe_env(self, name: str) -> bool:
        """删除执行环境"""
        return self._exe_registry.remove(name)

    # ---- 统一列表 ----

    def list_all(self) -> list[dict[str, Any]]:
        """列出所有环境（构建 + 执行）"""
        result: list[dict[str, Any]] = []
        for env in self._build_registry.list():
            result.append({"category": "build", **env})
        for env in self._exe_registry.list():
            result.append({"category": "exe", **env})
        return result

    # ---- 生命周期: apply / release / timeout / invalid ----

    def apply(
        self, *, build_env_name: str = "", exe_env_name: str = "",
    ) -> EnvSession:
        """申请环境，返回 session"""
        return self._lifecycle.apply(
            build_env_name=build_env_name,
            exe_env_name=exe_env_name,
        )

    def release(self, session: EnvSession) -> EnvSession:
        """释放环境"""
        return self._lifecycle.release(session)

    def timeout(self, session: EnvSession) -> EnvSession:
        """标记超时"""
        return self._lifecycle.timeout(session)

    def invalid(self, session: EnvSession) -> EnvSession:
        """标记失效"""
        return self._lifecycle.invalid(session)

    def get_session(self, session_id: str) -> EnvSession | None:
        """获取会话"""
        return self._lifecycle.get_session(session_id)

    def list_sessions(self) -> list[dict[str, str]]:
        """列出所有会话"""
        return self._lifecycle.list_sessions()

    # ---- 在环境中执行命令 ----

    def execute_in(
        self, session: EnvSession, cmd: str, *, timeout: int = 3600,
    ) -> dict[str, Any]:
        """在已申请的环境会话中执行命令"""
        return self._executor.execute_in(session, cmd, timeout=timeout)
