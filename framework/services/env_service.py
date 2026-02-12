"""环境服务 — 构建环境 + 执行环境的注册 / 申请 / 释放 / 超时 / 失效

环境分为两大类:
  构建环境 (BuildEnv): local（本地）/ remote（远端服务器）
  执行环境 (ExeEnv):   eda / fpga / silicon（均为 Web API）/ same_as_build

公共生命周期: apply → (timeout | release | invalid)

不同类型有独立的一套 API 实现，但共享公共接口:
  apply()   — 申请环境资源，获得 session
  timeout() — 标记超时
  release() — 释放环境
  invalid() — 标记失效

编排顺序: 环境优先于代码仓（环境决定代码仓检出位置）
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import tempfile
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import (
    BUILD_ENV_LOCAL,
    BUILD_ENV_REMOTE,
    BUILD_ENV_TYPES,
    ENV_APPLIED,
    ENV_INVALID,
    ENV_RELEASED,
    ENV_TIMEOUT,
    EXE_ENV_EDA,
    EXE_ENV_FPGA,
    EXE_ENV_SAME_AS_BUILD,
    EXE_ENV_SILICON,
    EXE_ENV_TYPES,
    BuildEnvSpec,
    EnvSession,
    ExeEnvSpec,
    ToolSpec,
)
from framework.core.registry import YamlRegistry

logger = logging.getLogger(__name__)


# =========================================================================
# 环境处理器抽象基类
# =========================================================================


class BaseEnvHandler(ABC):
    """环境处理器公共接口"""

    @abstractmethod
    def apply(self, session: EnvSession) -> EnvSession:
        """申请环境资源"""

    @abstractmethod
    def release(self, session: EnvSession) -> EnvSession:
        """释放环境资源"""

    def timeout(self, session: EnvSession) -> EnvSession:
        """标记超时"""
        session.status = ENV_TIMEOUT
        session.message = "环境超时"
        logger.warning("环境超时: %s", session.name)
        return session

    def invalid(self, session: EnvSession) -> EnvSession:
        """标记失效"""
        session.status = ENV_INVALID
        session.message = "环境已失效"
        logger.warning("环境失效: %s", session.name)
        return session


# =========================================================================
# 构建环境处理器
# =========================================================================


class LocalBuildHandler(BaseEnvHandler):
    """本地构建环境"""

    def apply(self, session: EnvSession) -> EnvSession:
        spec = session.build_env
        if spec is None:
            session.status = ENV_INVALID
            return session
        work = spec.work_dir or str(Path("data/workspaces") / session.name)
        Path(work).mkdir(parents=True, exist_ok=True)
        session.work_dir = work
        session.status = ENV_APPLIED
        session.resolved_vars.update(spec.variables)
        logger.info("本地构建环境已申请: %s -> %s", session.name, work)
        return session

    def release(self, session: EnvSession) -> EnvSession:
        session.status = ENV_RELEASED
        logger.info("本地构建环境已释放: %s", session.name)
        return session


class RemoteBuildHandler(BaseEnvHandler):
    """远端服务器构建环境（SSH）"""

    def apply(self, session: EnvSession) -> EnvSession:
        spec = session.build_env
        if spec is None or not spec.host:
            session.status = ENV_INVALID
            session.message = "远端构建环境缺少 host"
            return session
        work = spec.work_dir or os.path.join(
            tempfile.gettempdir(), "aieffect", session.name,
        )
        session.work_dir = work
        session.status = ENV_APPLIED
        session.resolved_vars.update(spec.variables)
        session.resolved_vars["REMOTE_HOST"] = spec.host
        session.resolved_vars["REMOTE_PORT"] = str(spec.port)
        session.resolved_vars["REMOTE_USER"] = spec.user
        logger.info("远端构建环境已申请: %s -> %s@%s:%s",
                     session.name, spec.user, spec.host, work)
        return session

    def release(self, session: EnvSession) -> EnvSession:
        session.status = ENV_RELEASED
        logger.info("远端构建环境已释放: %s", session.name)
        return session


# =========================================================================
# 执行环境处理器
# =========================================================================


class WebApiExeHandler(BaseEnvHandler):
    """Web API 执行环境基类（eda / fpga / silicon 共享）"""

    env_type_label: str = "WebAPI"

    def apply(self, session: EnvSession) -> EnvSession:
        spec = session.exe_env
        if spec is None or not spec.api_url:
            session.status = ENV_INVALID
            session.message = f"{self.env_type_label} 缺少 api_url"
            return session

        session.status = ENV_APPLIED
        session.resolved_vars.update(spec.variables)
        session.resolved_vars["API_URL"] = spec.api_url
        if spec.api_token:
            session.resolved_vars["API_TOKEN"] = spec.api_token

        # 工具链变量
        for tool in spec.tools.values():
            if tool.install_path:
                session.resolved_vars[f"{tool.name.upper()}_HOME"] = tool.install_path
            for vk, vv in tool.env_vars.items():
                session.resolved_vars[vk] = vv

        # 许可证
        for lk, lv in spec.licenses.items():
            session.resolved_vars[lk] = lv

        logger.info("%s 执行环境已申请: %s (api=%s)",
                     self.env_type_label, session.name, spec.api_url)
        return session

    def release(self, session: EnvSession) -> EnvSession:
        session.status = ENV_RELEASED
        logger.info("%s 执行环境已释放: %s", self.env_type_label, session.name)
        return session


class EdaExeHandler(WebApiExeHandler):
    """EDA 仿真执行环境"""
    env_type_label = "EDA"


class FpgaExeHandler(WebApiExeHandler):
    """FPGA 验证执行环境"""
    env_type_label = "FPGA"


class SiliconExeHandler(WebApiExeHandler):
    """样片测试执行环境"""
    env_type_label = "Silicon"


class SameAsBuildExeHandler(BaseEnvHandler):
    """同构建环境执行 — 复用构建环境的 work_dir 和变量"""

    def apply(self, session: EnvSession) -> EnvSession:
        if session.build_env is None:
            session.status = ENV_INVALID
            session.message = "same_as_build 需要关联构建环境"
            return session
        session.status = ENV_APPLIED
        logger.info("同构建执行环境已申请: %s", session.name)
        return session

    def release(self, session: EnvSession) -> EnvSession:
        session.status = ENV_RELEASED
        logger.info("同构建执行环境已释放: %s", session.name)
        return session


# =========================================================================
# 处理器工厂
# =========================================================================

_BUILD_HANDLERS: dict[str, type[BaseEnvHandler]] = {
    BUILD_ENV_LOCAL: LocalBuildHandler,
    BUILD_ENV_REMOTE: RemoteBuildHandler,
}

_EXE_HANDLERS: dict[str, type[BaseEnvHandler]] = {
    EXE_ENV_EDA: EdaExeHandler,
    EXE_ENV_FPGA: FpgaExeHandler,
    EXE_ENV_SILICON: SiliconExeHandler,
    EXE_ENV_SAME_AS_BUILD: SameAsBuildExeHandler,
}


def _get_build_handler(env_type: str) -> BaseEnvHandler:
    """根据环境类型获取构建环境处理器实例"""
    cls = _BUILD_HANDLERS.get(env_type)
    if cls is None:
        raise ValidationError(f"不支持的构建环境类型: {env_type}")
    return cls()


def _get_exe_handler(env_type: str) -> BaseEnvHandler:
    """根据环境类型获取执行环境处理器实例"""
    cls = _EXE_HANDLERS.get(env_type)
    if cls is None:
        raise ValidationError(f"不支持的执行环境类型: {env_type}")
    return cls()


# =========================================================================
# 环境服务
# =========================================================================


class EnvService(YamlRegistry):
    """环境全生命周期管理"""

    section_key = "build_envs"

    def __init__(self, registry_file: str = "") -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "envs_file", "data/environments.yml")
        super().__init__(registry_file)
        self._sessions: dict[str, EnvSession] = {}

    def _build_envs(self) -> dict[str, dict[str, Any]]:
        """获取构建环境配置字典"""
        return self._section()

    def _exe_envs(self) -> dict[str, dict[str, Any]]:
        """获取执行环境配置字典"""
        result: dict[str, dict[str, Any]] = self._data.setdefault("exe_envs", {})
        return result

    # ---- 构建环境 CRUD ----

    def register_build_env(self, spec: BuildEnvSpec) -> dict[str, Any]:
        """注册构建环境"""
        if not spec.name:
            raise ValidationError("构建环境 name 为必填")
        if spec.build_env_type not in BUILD_ENV_TYPES:
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
        self._save()
        logger.info("构建环境已注册: %s (type=%s)", spec.name, spec.build_env_type)
        return entry

    def get_build_env(self, name: str) -> BuildEnvSpec | None:
        entry = self._build_envs().get(name)
        if entry is None:
            return None
        return BuildEnvSpec(
            name=name,
            build_env_type=entry.get("build_env_type", BUILD_ENV_LOCAL),
            description=entry.get("description", ""),
            work_dir=entry.get("work_dir", ""),
            variables=entry.get("variables", {}),
            host=entry.get("host", ""),
            port=entry.get("port", 22),
            user=entry.get("user", ""),
            key_path=entry.get("key_path", ""),
        )

    def list_build_envs(self) -> list[dict[str, Any]]:
        return [{"name": k, **v} for k, v in self._build_envs().items()]

    def remove_build_env(self, name: str) -> bool:
        envs = self._build_envs()
        if name not in envs:
            return False
        del envs[name]
        self._save()
        return True

    # ---- 执行环境 CRUD ----

    def register_exe_env(self, spec: ExeEnvSpec) -> dict[str, Any]:
        """注册执行环境"""
        if not spec.name:
            raise ValidationError("执行环境 name 为必填")
        if spec.exe_env_type not in EXE_ENV_TYPES:
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
        self._save()
        logger.info("执行环境已注册: %s (type=%s)", spec.name, spec.exe_env_type)
        return entry

    def get_exe_env(self, name: str) -> ExeEnvSpec | None:
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
            exe_env_type=entry.get("exe_env_type", EXE_ENV_EDA),
            description=entry.get("description", ""),
            api_url=entry.get("api_url", ""),
            api_token=entry.get("api_token", ""),
            variables=entry.get("variables", {}),
            tools=tools,
            licenses=entry.get("licenses", {}),
            timeout=entry.get("timeout", 3600),
            build_env_name=entry.get("build_env_name", ""),
        )

    def list_exe_envs(self) -> list[dict[str, Any]]:
        return [{"name": k, **v} for k, v in self._exe_envs().items()]

    def remove_exe_env(self, name: str) -> bool:
        envs = self._exe_envs()
        if name not in envs:
            return False
        del envs[name]
        self._save()
        return True

    # ---- 统一列表 ----

    def list_all(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for name, info in self._build_envs().items():
            result.append({"name": name, "category": "build", **info})
        for name, info in self._exe_envs().items():
            result.append({"name": name, "category": "exe", **info})
        return result

    # ---- 生命周期: apply / release / timeout / invalid ----

    def apply(
        self, *, build_env_name: str = "", exe_env_name: str = "",
    ) -> EnvSession:
        """申请环境，返回 session"""
        session_id = str(uuid.uuid4())[:8]
        name = exe_env_name or build_env_name or "anonymous"
        session = EnvSession(name=name, session_id=session_id)

        if build_env_name:
            session = self._apply_build_env(session, build_env_name)
            if session.status != ENV_APPLIED:
                return session

        if exe_env_name:
            session = self._apply_exe_env(session, exe_env_name)

        self._sessions[session_id] = session
        logger.info("环境会话已创建: id=%s, name=%s, status=%s",
                     session_id, name, session.status)
        return session

    def _apply_build_env(
        self, session: EnvSession, build_env_name: str,
    ) -> EnvSession:
        spec = self.get_build_env(build_env_name)
        if spec is None:
            raise CaseNotFoundError(f"构建环境不存在: {build_env_name}")
        session.build_env = spec
        handler = _get_build_handler(spec.build_env_type)
        return handler.apply(session)

    def _apply_exe_env(
        self, session: EnvSession, exe_env_name: str,
    ) -> EnvSession:
        exe_spec = self.get_exe_env(exe_env_name)
        if exe_spec is None:
            raise CaseNotFoundError(f"执行环境不存在: {exe_env_name}")
        session.exe_env = exe_spec
        if exe_spec.exe_env_type == EXE_ENV_SAME_AS_BUILD and not session.build_env:
            session = self._auto_apply_linked_build(session, exe_spec)
        handler = _get_exe_handler(exe_spec.exe_env_type)
        return handler.apply(session)

    def _auto_apply_linked_build(
        self, session: EnvSession, exe_spec: ExeEnvSpec,
    ) -> EnvSession:
        if not exe_spec.build_env_name:
            return session
        bspec = self.get_build_env(exe_spec.build_env_name)
        if bspec is None:
            return session
        session.build_env = bspec
        bh = _get_build_handler(bspec.build_env_type)
        return bh.apply(session)

    def release(self, session: EnvSession) -> EnvSession:
        """释放环境"""
        if session.exe_env:
            h = _get_exe_handler(session.exe_env.exe_env_type)
            session = h.release(session)
        if session.build_env:
            h = _get_build_handler(session.build_env.build_env_type)
            session = h.release(session)
        session.status = ENV_RELEASED
        self._sessions.pop(session.session_id, None)
        return session

    def timeout(self, session: EnvSession) -> EnvSession:
        """标记超时"""
        session.status = ENV_TIMEOUT
        self._sessions.pop(session.session_id, None)
        return session

    def invalid(self, session: EnvSession) -> EnvSession:
        """标记失效"""
        session.status = ENV_INVALID
        self._sessions.pop(session.session_id, None)
        return session

    def get_session(self, session_id: str) -> EnvSession | None:
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict[str, str]]:
        return [
            {"session_id": s.session_id, "name": s.name, "status": s.status}
            for s in self._sessions.values()
        ]

    # ---- 在环境中执行命令 ----

    def execute_in(
        self, session: EnvSession, cmd: str, *, timeout: int = 3600,
    ) -> dict[str, Any]:
        """在已申请的环境会话中执行命令"""
        if session.status != ENV_APPLIED:
            raise ValidationError(f"环境会话状态不可用: {session.status}")

        env = {**os.environ, **session.resolved_vars}
        work_dir = session.work_dir or "."
        logger.info("执行命令: %s (session=%s)", cmd, session.session_id)

        try:
            result = subprocess.run(
                shlex.split(cmd),
                capture_output=True, text=True, timeout=timeout,
                cwd=work_dir, env=env, check=False,
            )
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            self.timeout(session)
            return {
                "returncode": -1, "stdout": "",
                "stderr": f"命令超时 ({timeout}s)", "success": False,
            }
