"""环境服务模块 - 模块化重构

拆分说明:
- handlers.py: 环境处理器 (~235 行)
- build_registry.py: 构建环境注册表 (~83 行)
- exe_registry.py: 执行环境注册表 (~104 行)
- lifecycle.py: 生命周期管理 (~129 行)
- executor.py: 命令执行器 (~59 行)

总计从 509 行拆分为 5 个模块
"""

from framework.services.env.build_registry import BuildEnvRegistry
from framework.services.env.exe_registry import ExeEnvRegistry
from framework.services.env.executor import EnvExecutor
from framework.services.env.handlers import (
    BaseEnvHandler,
    EdaExeHandler,
    FpgaExeHandler,
    LocalBuildHandler,
    RemoteBuildHandler,
    SameAsBuildExeHandler,
    SiliconExeHandler,
    WebApiExeHandler,
    get_build_handler,
    get_exe_handler,
)
from framework.services.env.lifecycle import EnvLifecycle

__all__ = [
    "BaseEnvHandler",
    "LocalBuildHandler",
    "RemoteBuildHandler",
    "WebApiExeHandler",
    "EdaExeHandler",
    "FpgaExeHandler",
    "SiliconExeHandler",
    "SameAsBuildExeHandler",
    "get_build_handler",
    "get_exe_handler",
    "BuildEnvRegistry",
    "ExeEnvRegistry",
    "EnvLifecycle",
    "EnvExecutor",
]
