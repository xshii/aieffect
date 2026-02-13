"""Shell 命令执行工具 — 统一子进程调用

通过 CommandExecutor 协议抽象子进程执行，方便测试替换和跨平台适配。
"""

from __future__ import annotations

import logging
import shlex
import subprocess
from dataclasses import dataclass
from typing import Protocol

from framework.core.exceptions import ExecutionError

logger = logging.getLogger(__name__)


# =========================================================================
# 命令执行结果
# =========================================================================

@dataclass
class CommandResult:
    """命令执行结果（与 subprocess 解耦）"""

    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0


# =========================================================================
# 命令执行器协议
# =========================================================================

class CommandExecutor(Protocol):
    """命令执行器协议 — 抽象子进程调用

    实现此协议即可替换底层执行方式（本地 shell、SSH 远程、Docker 等）。
    测试时可注入 mock 实现，无需 patch subprocess。
    """

    def execute(
        self,
        cmd: str | list[str],
        *,
        cwd: str = ".",
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        """执行命令并返回结果"""
        ...


# =========================================================================
# 默认实现: 本地 Shell 执行器
# =========================================================================

class LocalExecutor:
    """本地 Shell 命令执行器（默认实现）"""

    def execute(
        self,
        cmd: str | list[str],
        *,
        cwd: str = ".",
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> CommandResult:
        args = shlex.split(cmd) if isinstance(cmd, str) else cmd
        r = subprocess.run(
            args, capture_output=True, text=True,
            cwd=cwd, env=env, check=False, timeout=timeout,
        )
        return CommandResult(
            returncode=r.returncode,
            stdout=r.stdout,
            stderr=r.stderr,
        )


# =========================================================================
# 全局默认执行器（可替换）
# =========================================================================

_default_executor: CommandExecutor = LocalExecutor()


def get_executor() -> CommandExecutor:
    """获取全局默认命令执行器"""
    return _default_executor


def set_executor(executor: CommandExecutor) -> None:
    """替换全局默认命令执行器（用于测试或远程执行场景）"""
    global _default_executor  # noqa: PLW0603
    _default_executor = executor


# =========================================================================
# 便捷函数（向后兼容）
# =========================================================================

def run_cmd(
    cmd: str, *, cwd: str = ".",
    env: dict[str, str] | None = None,
    label: str = "cmd",
) -> subprocess.CompletedProcess[str]:
    """执行 shell 命令，失败抛 ExecutionError

    Args:
        cmd: 命令字符串
        cwd: 工作目录
        env: 环境变量（不传则继承当前进程）
        label: 日志标签
    """
    logger.info("  %s: %s (cwd=%s)", label, cmd, cwd)
    r = subprocess.run(
        shlex.split(cmd), capture_output=True, text=True,
        cwd=cwd, env=env, check=False,
    )
    if r.returncode != 0:
        raise ExecutionError(f"{label}失败 (rc={r.returncode}): {r.stderr[:500]}")
    return r
