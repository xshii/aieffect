"""环境命令执行器

职责:
- 在已申请的环境会话中执行命令
- 处理超时和环境变量
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.services.env.lifecycle import EnvLifecycle

from framework.core.exceptions import ValidationError
from framework.core.models import EnvSession, EnvStatus

logger = logging.getLogger(__name__)


class EnvExecutor:
    """环境命令执行器"""

    def __init__(self, lifecycle: EnvLifecycle) -> None:
        self._lifecycle = lifecycle

    def execute_in(
        self, session: EnvSession, cmd: str, *, timeout: int = 3600,
    ) -> dict[str, Any]:
        """在已申请的环境会话中执行命令"""
        if session.status != EnvStatus.APPLIED:
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
            self._lifecycle.timeout(session)
            return {
                "returncode": -1, "stdout": "",
                "stderr": f"命令超时 ({timeout}s)", "success": False,
            }
