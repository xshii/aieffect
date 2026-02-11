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
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from framework.core.exceptions import CaseNotFoundError, ValidationError
from framework.core.models import BuildResult, BuildSpec
from framework.utils.yaml_io import load_yaml, save_yaml

logger = logging.getLogger(__name__)


class BuildService:
    """构建生命周期管理"""

    def __init__(self, registry_file: str = "", output_root: str = "") -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "builds_file", "data/builds.yml")
        if not output_root:
            from framework.core.config import get_config
            output_root = str(Path(get_config().workspace_dir) / "builds")
        self.registry_file = Path(registry_file)
        self.output_root = Path(output_root)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = load_yaml(self.registry_file)
        # 构建缓存: (build_name, repo_ref) -> BuildResult
        self._build_cache: dict[tuple[str, str], BuildResult] = {}

    def _builds(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = self._data.setdefault("builds", {})
        return result

    def _save(self) -> None:
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        save_yaml(self.registry_file, self._data)

    # ---- 注册 / CRUD ----

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
        self._builds()[spec.name] = entry
        self._save()
        logger.info("构建配置已注册: %s", spec.name)
        return entry

    def get(self, name: str) -> BuildSpec | None:
        """获取已注册构建定义"""
        entry = self._builds().get(name)
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
        """列出所有已注册构建配置"""
        return [{"name": k, **v} for k, v in self._builds().items()]

    def remove(self, name: str) -> bool:
        """移除构建注册"""
        builds = self._builds()
        if name not in builds:
            return False
        del builds[name]
        self._save()
        # 清理关联缓存
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
        """执行构建流程

        缓存策略:
          - 以 (name, repo_ref) 为缓存键
          - 同名同分支已成功构建过则直接返回缓存结果
          - 指定新分支时 repo_ref 不同，缓存未命中，触发重建
          - force=True 时强制重新构建
        """
        spec = self.get(name)
        if spec is None:
            raise CaseNotFoundError(f"构建配置不存在: {name}")

        # 解析代码仓分支
        effective_ref = repo_ref
        if not effective_ref and spec.repo_name:
            from framework.services.repo_service import RepoService
            svc = RepoService()
            repo_spec = svc.get(spec.repo_name)
            if repo_spec:
                effective_ref = repo_spec.ref

        # 检查构建缓存
        cache_key = (name, effective_ref)
        if not force and cache_key in self._build_cache:
            cached = self._build_cache[cache_key]
            if cached.status == "success":
                logger.info(
                    "构建缓存命中: %s (ref=%s), 跳过重复构建",
                    name, effective_ref,
                )
                return BuildResult(
                    spec=spec,
                    output_path=cached.output_path,
                    status="cached",
                    duration=cached.duration,
                    message=f"缓存命中 (ref={effective_ref})",
                    repo_ref=effective_ref,
                    cached=True,
                )

        # 解析工作目录
        if not work_dir:
            if spec.repo_name:
                from framework.services.repo_service import RepoService
                svc = RepoService()
                ws = svc.checkout(spec.repo_name, ref_override=repo_ref)
                if ws.status == "error":
                    return BuildResult(
                        spec=spec, status="failed",
                        message="代码仓检出失败", repo_ref=effective_ref,
                    )
                work_dir = ws.local_path
            else:
                work_dir = str(self.output_root / name)
                Path(work_dir).mkdir(parents=True, exist_ok=True)

        import os
        env = {**os.environ, **(env_vars or {})}
        start = time.monotonic()

        try:
            if spec.setup_cmd:
                self._run_cmd(spec.setup_cmd, work_dir, env, "setup")
            if spec.build_cmd:
                self._run_cmd(spec.build_cmd, work_dir, env, "build")
        except RuntimeError as e:
            duration = time.monotonic() - start
            logger.error("构建失败 %s: %s", name, e)
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
        # 写入缓存
        self._build_cache[cache_key] = result
        logger.info(
            "构建完成: %s (ref=%s, %.1fs) -> %s",
            name, effective_ref, duration, output_path,
        )
        return result

    def is_cached(self, name: str, repo_ref: str = "") -> bool:
        """检查构建是否已缓存"""
        cache_key = (name, repo_ref)
        cached = self._build_cache.get(cache_key)
        return cached is not None and cached.status == "success"

    def invalidate_cache(self, name: str, repo_ref: str = "") -> bool:
        """失效指定构建缓存"""
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
        """执行清理命令"""
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
            import os
            self._run_cmd(spec.clean_cmd, work_dir, dict(os.environ), "clean")
            self.invalidate_cache(name)
            return True
        except RuntimeError as e:
            logger.error("清理失败 %s: %s", name, e)
            return False

    @staticmethod
    def _run_cmd(cmd: str, cwd: str, env: dict[str, str], label: str) -> None:
        logger.info("  %s: %s (cwd=%s)", label, cmd, cwd)
        r = subprocess.run(
            shlex.split(cmd), capture_output=True, text=True,
            cwd=cwd, env=env, check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"{label}失败 (rc={r.returncode}): {r.stderr[:500]}")
