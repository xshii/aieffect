"""测试调度器 - 管理用例的并行执行

通过策略模式注入仓库准备逻辑（RepoPreparer），消除与 git/dep 的直接耦合。
默认使用 RepoService 实现仓库操作，也可在测试中替换为 mock。
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from framework.core.models import Case, TaskResult
from framework.core.resource import ResourceManager
from framework.utils.shell import run_cmd

logger = logging.getLogger(__name__)

# 仓库准备策略类型：接受 repo dict，返回工作目录路径或 None
RepoPreparer = Callable[[dict[str, str]], "Path | None"]

_SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9_./@\-]+$")


def _default_prepare_repo(repo: dict[str, str]) -> Path | None:
    """默认仓库准备策略 — 保持原有行为，但复用 shell.run_cmd"""
    url = repo.get("url", "")
    if not url:
        return None

    ref = repo.get("ref", "main")
    if not _SAFE_REF_RE.match(ref):
        raise ValueError(f"ref 包含非法字符: {ref}")

    from framework.core.config import get_config
    repo_name = url.rstrip("/").split("/")[-1].removesuffix(".git")
    workspace = Path(get_config().workspace_dir) / repo_name / ref.replace("/", "_")
    workspace.mkdir(parents=True, exist_ok=True)

    _clone_or_fetch(url, ref, workspace)

    cwd = workspace / repo.get("path", "") if repo.get("path") else workspace
    if not cwd.exists():
        raise FileNotFoundError(f"仓库子目录不存在: {cwd}")

    if repo.get("setup"):
        run_cmd(repo["setup"], cwd=str(cwd), label="安装依赖")
    if repo.get("build"):
        run_cmd(repo["build"], cwd=str(cwd), label="编译")

    return cwd


def _clone_or_fetch(url: str, ref: str, workspace: Path) -> None:
    """clone 或 fetch+checkout 仓库"""
    if (workspace / ".git").exists():
        logger.info("  更新仓库: %s@%s", url.split("/")[-1], ref)
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", ref],
            cwd=str(workspace), capture_output=True, check=False,
        )
        subprocess.run(
            ["git", "checkout", "FETCH_HEAD"],
            cwd=str(workspace), capture_output=True, check=False,
        )
    else:
        logger.info("  克隆仓库: %s@%s -> %s", url, ref, workspace)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--branch", ref, url, str(workspace)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode != 0:
            subprocess.run(
                ["git", "clone", url, str(workspace)],
                capture_output=True, text=True, check=False,
            )
            subprocess.run(
                ["git", "checkout", ref],
                cwd=str(workspace), capture_output=True, check=False,
            )


def _prepare_repo(repo: dict[str, str]) -> Path | None:
    """向后兼容入口 — 委托 _default_prepare_repo"""
    return _default_prepare_repo(repo)


class Scheduler:
    """可配置并行度的测试调度器

    支持可选的 ResourceManager 集成：执行前 acquire，执行后 release，
    资源不足时等待或跳过。

    通过 repo_preparer 参数注入仓库准备策略（Strategy 模式），
    默认使用 _default_prepare_repo，测试时可替换为 mock。
    """

    def __init__(
        self,
        max_workers: int = 1,
        resource_manager: ResourceManager | None = None,
        repo_preparer: RepoPreparer | None = None,
    ) -> None:
        self.max_workers = max(1, max_workers)
        self.resource_mgr = resource_manager
        self._repo_preparer = repo_preparer or _default_prepare_repo

    @staticmethod
    def _err(name: str, start: float, msg: str) -> TaskResult:
        return TaskResult(name=name, status="error", duration=time.monotonic() - start, message=msg)

    def _resolve_cwd(self, case: Case) -> str | None:
        """准备外部仓库工作目录，无仓库配置时返回 None"""
        if not case.repo or not case.repo.get("url"):
            return None
        repo_dir = self._repo_preparer(case.repo)
        return str(repo_dir) if repo_dir else None

    def _run_command(self, case: Case, cwd: str | None) -> TaskResult:
        """执行 shell 命令并返回结果"""
        cmd = case.args.get("cmd", "")
        start = time.monotonic()

        logger.info("执行: %s -> %s%s", case.name, cmd, f" (cwd={cwd})" if cwd else "")

        result = subprocess.run(
            shlex.split(cmd), capture_output=True, text=True,
            timeout=case.timeout, cwd=cwd, check=False,
        )
        duration = time.monotonic() - start
        success = result.returncode == 0
        return TaskResult(
            name=case.name,
            status="passed" if success else "failed",
            duration=duration,
            message="通过" if success else f"退出码: {result.returncode}\n{result.stderr[:500]}",
        )

    def _execute_one(self, case: Case) -> TaskResult:
        """通过 shell 命令执行单个测试用例"""
        if self.resource_mgr:
            if not self.resource_mgr.acquire(task_name=case.name):
                return TaskResult(name=case.name, status="skipped", message="资源不足，跳过执行")

        start = time.monotonic()
        try:
            if not case.args.get("cmd", ""):
                return TaskResult(name=case.name, status="skipped", message="用例 args 中未定义 'cmd' 命令")

            cwd = self._resolve_cwd(case)
            return self._run_command(case, cwd)
        except (ValueError, FileNotFoundError, RuntimeError) as e:
            return self._err(case.name, start, f"仓库准备失败: {e}")
        except subprocess.TimeoutExpired:
            return self._err(case.name, start, f"超时（{case.timeout}秒）")
        except OSError as e:
            logger.exception("执行用例 '%s' 时出错", case.name)
            return self._err(case.name, start, str(e))
        finally:
            if self.resource_mgr:
                self.resource_mgr.release(task_name=case.name)

    def run_all(self, cases: list[Case]) -> list[TaskResult]:
        """并行控制下执行所有用例，返回结果与输入顺序一致"""
        if self.max_workers == 1:
            results: list[TaskResult] = []
            for case in cases:
                logger.info("执行: %s", case.name)
                results.append(self._execute_one(case))
            return results

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self._execute_one, c) for c in cases]
            results = []
            for case, future in zip(cases, futures):
                result = future.result()
                logger.info("完成: %s -> %s (%.1f秒)", case.name, result.status, result.duration)
                results.append(result)
            return results
