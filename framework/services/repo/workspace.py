"""工作空间管理 - 列出和清理本地工作目录

职责：
- 列出所有已检出的工作目录
- 清理指定代码仓的工作目录
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.services.repo.checkout import RepoCheckout

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """工作空间管理器"""

    def __init__(self, workspace_root: str = "", checkout: RepoCheckout | None = None) -> None:
        if not workspace_root:
            from framework.core.config import get_config
            workspace_root = get_config().workspace_dir
        self.workspace_root = Path(workspace_root)
        self._checkout = checkout

    def list_workspaces(self) -> list[dict[str, str]]:
        """列出本地已检出的工作目录"""
        result: list[dict[str, str]] = []
        if not self.workspace_root.exists():
            return result
        for repo_dir in sorted(self.workspace_root.iterdir()):
            if not repo_dir.is_dir():
                continue
            for ref_dir in sorted(repo_dir.iterdir()):
                if not ref_dir.is_dir():
                    continue
                is_git = (ref_dir / ".git").exists()
                sha = self._get_commit_sha(ref_dir) if is_git else ""
                result.append({
                    "repo": repo_dir.name,
                    "ref": ref_dir.name,
                    "path": str(ref_dir),
                    "commit": sha,
                    "type": "git" if is_git else "extracted",
                })
        return result

    def clean(self, name: str) -> int:
        """清理代码仓本地工作目录，返回清理的目录数"""
        repo_dir = self.workspace_root / name
        if not repo_dir.exists():
            return 0
        import shutil
        count = 0
        for child in repo_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                count += 1

        # 清理 checkout 缓存
        if self._checkout is not None:
            self._checkout.clear_cache(name)

        logger.info("已清理 %s 的 %d 个工作目录", name, count)
        return count

    @staticmethod
    def _get_commit_sha(workspace: Path) -> str:
        """获取 Git commit SHA"""
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True, check=False,
        )
        return r.stdout.strip()[:12] if r.returncode == 0 else ""
