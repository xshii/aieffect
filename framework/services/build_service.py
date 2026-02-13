"""构建服务 — 构建定义注册 / 执行 / 缓存

管理「代码仓 → 编译 → 产物」的构建流程，
支持构建缓存复用和产物生命周期管理。

缓存策略:
  - 以 (build_name, repo_ref) 为缓存键
  - 同名同分支不重复构建
  - 指定新分支时自动重新构建
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.services.repo_service import RepoService

from framework.core.exceptions import CaseNotFoundError, ExecutionError, ValidationError
from framework.core.models import BuildResult, BuildSpec
from framework.core.registry import YamlRegistry
from framework.utils.shell import run_cmd

logger = logging.getLogger(__name__)


class BuildService(YamlRegistry):
    """构建生命周期管理"""

    section_key = "builds"

    def __init__(
        self, registry_file: str, output_root: str,
        repo_service: RepoService | None = None,
    ) -> None:
        super().__init__(registry_file)
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._build_cache: dict[tuple[str, str], BuildResult] = {}
        self._repo_service = repo_service

    def _get_repo_service(self) -> RepoService:
        if self._repo_service is not None:
            return self._repo_service
        from framework.services.repo_service import RepoService
        return RepoService()

    # ---- 注册 / CRUD ----

    @staticmethod
    def create_spec(data: dict[str, Any]) -> BuildSpec:
        """从字典创建 BuildSpec（CLI/Web 共用工厂）"""
        return BuildSpec(
            name=data.get("name", ""), repo_name=data.get("repo_name", ""),
            setup_cmd=data.get("setup_cmd", ""),
            build_cmd=data.get("build_cmd", ""),
            clean_cmd=data.get("clean_cmd", ""),
            output_dir=data.get("output_dir", ""),
        )

    def register(self, spec: BuildSpec) -> dict[str, str]:
        """注册构建配置"""
        if not spec.name:
            raise ValidationError("构建 name 为必填")
        entry: dict[str, str] = {
            "repo_name": spec.repo_name,
            "setup_cmd": spec.setup_cmd,
            "build_cmd": spec.build_cmd,
            "clean_cmd": spec.clean_cmd,
            "output_dir": spec.output_dir,
        }
        self._put(spec.name, entry)
        logger.info("构建配置已注册: %s", spec.name)
        return entry

    def get(self, name: str) -> BuildSpec | None:
        """获取已注册构建定义"""
        entry = self._get_raw(name)
        if entry is None:
            return None
        return BuildSpec(
            name=name,
            repo_name=entry.get("repo_name", ""),
            setup_cmd=entry.get("setup_cmd", ""),
            build_cmd=entry.get("build_cmd", ""),
            clean_cmd=entry.get("clean_cmd", ""),
            output_dir=entry.get("output_dir", ""),
        )

    def list_all(self) -> list[dict[str, Any]]:
        return self._list_raw()

    def remove(self, name: str) -> bool:
        if not self._remove(name):
            return False
        keys_to_remove = [k for k in self._build_cache if k[0] == name]
        for k in keys_to_remove:
            del self._build_cache[k]
        logger.info("构建已移除: %s", name)
        return True

    # ---- 执行构建 ----

    def build(
        self, name: str, *,
        work_dir: str = "",
        env_vars: dict[str, str] | None = None,
        repo_ref: str = "",
        force: bool = False,
    ) -> BuildResult:
        """执行构建流程（缓存策略见模块文档）"""
        spec = self.get(name)
        if spec is None:
            raise CaseNotFoundError(f"构建配置不存在: {name}")

        effective_ref = self._resolve_ref(spec, repo_ref)
        cached = self._check_cache(spec, effective_ref, force)
        if cached is not None:
            return cached

        work_dir = self._resolve_work_dir(spec, work_dir, repo_ref)
        if work_dir.startswith("ERROR:"):
            return BuildResult(
                spec=spec, status="failed",
                message=work_dir.removeprefix("ERROR:"), repo_ref=effective_ref,
            )
        return self._execute_build(spec, work_dir, env_vars, effective_ref)

    def _resolve_ref(self, spec: BuildSpec, repo_ref: str) -> str:
        """解析构建使用的代码分支，优先使用传入的ref，否则使用仓库默认ref"""
        if repo_ref:
            return repo_ref
        if spec.repo_name:
            repo_spec = self._get_repo_service().get(spec.repo_name)
            if repo_spec is not None:
                return str(repo_spec.ref)
        return ""

    def _check_cache(
        self, spec: BuildSpec, ref: str, force: bool,
    ) -> BuildResult | None:
        """检查构建缓存，返回缓存结果或None（未命中或force=True）"""
        cache_key = (spec.name, ref)
        if force or cache_key not in self._build_cache:
            return None
        cached = self._build_cache[cache_key]
        if cached.status != "success":
            return None
        logger.info("构建缓存命中: %s (ref=%s)", spec.name, ref)
        return BuildResult(
            spec=spec, output_path=cached.output_path,
            status="cached", duration=cached.duration,
            message=f"缓存命中 (ref={ref})",
            repo_ref=ref, cached=True,
        )

    def _resolve_work_dir(self, spec: BuildSpec, work_dir: str, repo_ref: str) -> str:
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

    def _execute_build(
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
        except ExecutionError as e:
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
        result = BuildResult(
            spec=spec, output_path=output_path,
            status="success", duration=duration, repo_ref=effective_ref,
        )
        self._build_cache[(spec.name, effective_ref)] = result
        logger.info("构建完成: %s (ref=%s, %.1fs)", spec.name, effective_ref, duration)
        return result

    def is_cached(self, name: str, repo_ref: str = "") -> bool:
        cached = self._build_cache.get((name, repo_ref))
        return cached is not None and cached.status == "success"

    def invalidate_cache(self, name: str, repo_ref: str = "") -> bool:
        if repo_ref:
            key = (name, repo_ref)
            if key in self._build_cache:
                del self._build_cache[key]
                return True
            return False
        keys = [k for k in self._build_cache if k[0] == name]
        for k in keys:
            del self._build_cache[k]
        return len(keys) > 0

    def clean(self, name: str, *, work_dir: str = "") -> bool:
        spec = self.get(name)
        if spec is None:
            return False
        if not spec.clean_cmd:
            logger.info("构建 %s 未定义清理命令", name)
            return True
        if not work_dir:
            work_dir = str(self.output_root / name)
        if not Path(work_dir).exists():
            return True
        try:
            run_cmd(spec.clean_cmd, cwd=work_dir, label="clean")
            self.invalidate_cache(name)
            return True
        except ExecutionError as e:
            logger.error("清理失败 %s: %s", name, e)
            return False
