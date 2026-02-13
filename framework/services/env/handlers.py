"""环境处理器 - Strategy Pattern

职责:
- 定义环境处理器公共接口
- 实现各类型环境的 apply/release/timeout/invalid 逻辑
- 提供处理器工厂函数

环境类型:
- 构建环境: local, remote
- 执行环境: eda, fpga, silicon, same_as_build
"""

from __future__ import annotations

import logging
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from framework.core.exceptions import ValidationError
from framework.core.models import (
    BuildEnvType,
    EnvSession,
    EnvStatus,
    ExeEnvType,
)

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
        session.status = EnvStatus.TIMEOUT
        session.message = "环境超时"
        logger.warning("环境超时: %s", session.name)
        return session

    def invalid(self, session: EnvSession) -> EnvSession:
        """标记失效"""
        session.status = EnvStatus.INVALID
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
            session.status = EnvStatus.INVALID
            return session
        work = spec.work_dir or str(Path("data/workspaces") / session.name)
        Path(work).mkdir(parents=True, exist_ok=True)
        session.work_dir = work
        session.status = EnvStatus.APPLIED
        session.resolved_vars.update(spec.variables)
        logger.info("本地构建环境已申请: %s -> %s", session.name, work)
        return session

    def release(self, session: EnvSession) -> EnvSession:
        session.status = EnvStatus.RELEASED
        logger.info("本地构建环境已释放: %s", session.name)
        return session


class RemoteBuildHandler(BaseEnvHandler):
    """远端服务器构建环境（SSH）"""

    def apply(self, session: EnvSession) -> EnvSession:
        spec = session.build_env
        if spec is None or not spec.host:
            session.status = EnvStatus.INVALID
            session.message = "远端构建环境缺少 host"
            return session
        work = spec.work_dir or os.path.join(
            tempfile.gettempdir(), "aieffect", session.name,
        )
        session.work_dir = work
        session.status = EnvStatus.APPLIED
        session.resolved_vars.update(spec.variables)
        session.resolved_vars["REMOTE_HOST"] = spec.host
        session.resolved_vars["REMOTE_PORT"] = str(spec.port)
        session.resolved_vars["REMOTE_USER"] = spec.user
        logger.info("远端构建环境已申请: %s -> %s@%s:%s",
                     session.name, spec.user, spec.host, work)
        return session

    def release(self, session: EnvSession) -> EnvSession:
        session.status = EnvStatus.RELEASED
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
            session.status = EnvStatus.INVALID
            session.message = f"{self.env_type_label} 缺少 api_url"
            return session

        session.status = EnvStatus.APPLIED
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
        session.status = EnvStatus.RELEASED
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
            session.status = EnvStatus.INVALID
            session.message = "same_as_build 需要关联构建环境"
            return session
        session.status = EnvStatus.APPLIED
        logger.info("同构建执行环境已申请: %s", session.name)
        return session

    def release(self, session: EnvSession) -> EnvSession:
        session.status = EnvStatus.RELEASED
        logger.info("同构建执行环境已释放: %s", session.name)
        return session


# =========================================================================
# 处理器工厂
# =========================================================================

_BUILD_HANDLERS: dict[str, type[BaseEnvHandler]] = {
    BuildEnvType.LOCAL: LocalBuildHandler,
    BuildEnvType.REMOTE: RemoteBuildHandler,
}

_EXE_HANDLERS: dict[str, type[BaseEnvHandler]] = {
    ExeEnvType.EDA: EdaExeHandler,
    ExeEnvType.FPGA: FpgaExeHandler,
    ExeEnvType.SILICON: SiliconExeHandler,
    ExeEnvType.SAME_AS_BUILD: SameAsBuildExeHandler,
}


def get_build_handler(env_type: str) -> BaseEnvHandler:
    """根据环境类型获取构建环境处理器实例"""
    cls = _BUILD_HANDLERS.get(env_type)
    if cls is None:
        raise ValidationError(f"不支持的构建环境类型: {env_type}")
    return cls()


def get_exe_handler(env_type: str) -> BaseEnvHandler:
    """根据环境类型获取执行环境处理器实例"""
    cls = _EXE_HANDLERS.get(env_type)
    if cls is None:
        raise ValidationError(f"不支持的执行环境类型: {env_type}")
    return cls()
