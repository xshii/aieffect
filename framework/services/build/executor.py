"""构建执行器

职责:
- 构建命令执行 (setup → build)
- 工作目录解析
- 代码分支解析
- 清理操作
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.services.repo_service import RepoService

from framework.core.models import BuildResult, BuildSpec
from framework.utils.shell import run_cmd

logger = logging.getLogger(__name__)


class BuildExecutor:
    """构建执行器"""

    def __init__(self, output_root: Path, repo_service: RepoService | None = None) -> None:
        self.output_root = output_root
        self._repo_service = repo_service

    def _get_repo_service(self) -> RepoService:
        """获取代码仓服务实例"""
        if self._repo_service is not None:
            return self._repo_service
        from framework.services.repo_service import RepoService
        return RepoService()

    def resolve_ref(self, spec: BuildSpec, repo_ref: str) -> str:
        """解析构建使用的代码分支，优先使用传入的ref，否则使用仓库默认ref"""
        if repo_ref:
            return repo_ref
        if spec.repo_name:
            repo_spec = self._get_repo_service().get(spec.repo_name)
            if repo_spec is not None:
                return str(repo_spec.ref)
        return ""

    def resolve_work_dir(self, spec: BuildSpec, work_dir: str, repo_ref: str) -> str:
        """解析构建工作目录，优先使用传入路径，否则自动checkout代码仓"""
        if work_dir:
            return work_dir
        if spec.repo_name:
            ws = self._get_repo_service().checkout(spec.repo_name, ref_override=repo_ref)
            if ws.status == "error":
                return "ERROR:代码仓检出失败"
            return str(ws.local_path)
        path = str(self.output_root / spec.name)
        Path(path).mkdir(parents=True, exist_ok=True)
        return path

    def execute(
        self, spec: BuildSpec, work_dir: str,
        env_vars: dict[str, str] | None, effective_ref: str,
    ) -> BuildResult:
        """执行实际的构建命令（setup → build），返回构建结果"""
        import os
        env = {**os.environ, **(env_vars or {})}
        start = time.monotonic()
        try:
            if spec.setup_cmd:
                run_cmd(spec.setup_cmd, cwd=work_dir, env=env, label="setup")
            if spec.build_cmd:
                run_cmd(spec.build_cmd, cwd=work_dir, env=env, label="build")
        except RuntimeError as e:
            duration = time.monotonic() - start
            logger.error("构建失败 %s: %s", spec.name, e)
            return BuildResult(
                spec=spec, status="failed", duration=duration,
                message=str(e), repo_ref=effective_ref,
            )
        duration = time.monotonic() - start
        output_path = (
            str(Path(work_dir) / spec.output_dir) if spec.output_dir else work_dir
        )
        logger.info("构建完成: %s (ref=%s, %.1fs)", spec.name, effective_ref, duration)
        return BuildResult(
            spec=spec, output_path=output_path,
            status="success", duration=duration, repo_ref=effective_ref,
        )

    def clean(self, spec: BuildSpec, work_dir: str = "") -> bool:
        """清理构建产物"""
        if not spec.clean_cmd:
            logger.info("构建 %s 未定义清理命令", spec.name)
            return True
        if not work_dir:
            work_dir = str(self.output_root / spec.name)
        if not Path(work_dir).exists():
            return True
        try:
            run_cmd(spec.clean_cmd, cwd=work_dir, label="clean")
            return True
        except RuntimeError as e:
            logger.error("清理失败 %s: %s", spec.name, e)
            return False
