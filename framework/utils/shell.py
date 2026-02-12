"""Shell 命令执行工具 — 统一子进程调用"""

from __future__ import annotations

import logging
import shlex
import subprocess

logger = logging.getLogger(__name__)


def run_cmd(
    cmd: str, *, cwd: str = ".",
    env: dict[str, str] | None = None,
    label: str = "cmd",
) -> subprocess.CompletedProcess[str]:
    """执行 shell 命令，失败抛 RuntimeError

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
        raise RuntimeError(f"{label}失败 (rc={r.returncode}): {r.stderr[:500]}")
    return r
