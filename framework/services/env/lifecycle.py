"""环境生命周期管理

职责:
- 环境申请 (apply)
- 环境释放 (release)
- 超时/失效标记 (timeout/invalid)
- 会话管理
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.services.env.build_registry import BuildEnvRegistry
    from framework.services.env.exe_registry import ExeEnvRegistry

from framework.core.exceptions import CaseNotFoundError
from framework.core.models import EnvSession, EnvStatus, ExeEnvSpec, ExeEnvType
from framework.services.env.handlers import get_build_handler, get_exe_handler

logger = logging.getLogger(__name__)


class EnvLifecycle:
    """环境生命周期管理器"""

    def __init__(
        self,
        build_registry: BuildEnvRegistry,
        exe_registry: ExeEnvRegistry,
    ) -> None:
        self._build_registry = build_registry
        self._exe_registry = exe_registry
        self._sessions: dict[str, EnvSession] = {}

    def apply(
        self, *, build_env_name: str = "", exe_env_name: str = "",
    ) -> EnvSession:
        """申请环境，返回 session"""
        session_id = str(uuid.uuid4())[:8]
        name = exe_env_name or build_env_name or "anonymous"
        session = EnvSession(name=name, session_id=session_id)

        if build_env_name:
            session = self._apply_build_env(session, build_env_name)
            if session.status != EnvStatus.APPLIED:
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
        spec = self._build_registry.get(build_env_name)
        if spec is None:
            raise CaseNotFoundError(f"构建环境不存在: {build_env_name}")
        session.build_env = spec
        handler = get_build_handler(spec.build_env_type)
        return handler.apply(session)

    def _apply_exe_env(
        self, session: EnvSession, exe_env_name: str,
    ) -> EnvSession:
        exe_spec = self._exe_registry.get(exe_env_name)
        if exe_spec is None:
            raise CaseNotFoundError(f"执行环境不存在: {exe_env_name}")
        session.exe_env = exe_spec
        if exe_spec.exe_env_type == ExeEnvType.SAME_AS_BUILD and not session.build_env:
            session = self._auto_apply_linked_build(session, exe_spec)
        handler = get_exe_handler(exe_spec.exe_env_type)
        return handler.apply(session)

    def _auto_apply_linked_build(
        self, session: EnvSession, exe_spec: ExeEnvSpec,
    ) -> EnvSession:
        if not exe_spec.build_env_name:
            return session
        bspec = self._build_registry.get(exe_spec.build_env_name)
        if bspec is None:
            return session
        session.build_env = bspec
        bh = get_build_handler(bspec.build_env_type)
        return bh.apply(session)

    def release(self, session: EnvSession) -> EnvSession:
        """释放环境"""
        if session.exe_env:
            h = get_exe_handler(session.exe_env.exe_env_type)
            session = h.release(session)
        if session.build_env:
            h = get_build_handler(session.build_env.build_env_type)
            session = h.release(session)
        session.status = EnvStatus.RELEASED
        self._sessions.pop(session.session_id, None)
        return session

    def timeout(self, session: EnvSession) -> EnvSession:
        """标记超时"""
        session.status = EnvStatus.TIMEOUT
        self._sessions.pop(session.session_id, None)
        return session

    def invalid(self, session: EnvSession) -> EnvSession:
        """标记失效"""
        session.status = EnvStatus.INVALID
        self._sessions.pop(session.session_id, None)
        return session

    def get_session(self, session_id: str) -> EnvSession | None:
        """获取会话"""
        return self._sessions.get(session_id)

    def list_sessions(self) -> list[dict[str, str]]:
        """列出所有会话"""
        return [
            {"session_id": s.session_id, "name": s.name, "status": s.status}
            for s in self._sessions.values()
        ]
