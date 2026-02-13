"""构建服务 — 门面接口

职责:
- 统一的构建服务 API
- 协调 registry、cache、executor

重构说明:
- 原 233 行拆分为 4 个模块
- 门面类 (46 行): 统一接口和协调
- build/registry.py (68 行): 配置管理
- build/cache.py (76 行): 缓存策略
- build/executor.py (118 行): 执行逻辑

管理「代码仓 → 编译 → 产物」的构建流程，
支持构建缓存复用和产物生命周期管理。

缓存策略:
  - 以 (build_name, repo_ref) 为缓存键
  - 同名同分支不重复构建
  - 指定新分支时自动重新构建
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.services.repo_service import RepoService

from framework.core.exceptions import CaseNotFoundError
from framework.core.models import BuildResult, BuildSpec
from framework.services.build import BuildCache, BuildExecutor, BuildRegistry


class BuildService:
    """构建生命周期管理（门面）"""

    def __init__(
        self, registry_file: str = "", output_root: str = "",
        repo_service: RepoService | None = None,
    ) -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "builds_file", "data/builds.yml")
        if not output_root:
            from framework.core.config import get_config
            output_root = str(Path(get_config().workspace_dir) / "builds")
        self._registry = BuildRegistry(registry_file)
        self._cache = BuildCache()
        self._executor = BuildExecutor(Path(output_root), repo_service)

    # ---- 委托: 注册管理 ----

    def register(self, spec: BuildSpec) -> dict[str, str]:
        return self._registry.register(spec)

    def get(self, name: str) -> BuildSpec | None:
        return self._registry.get(name)

    def list_all(self) -> list[dict[str, Any]]:
        return self._registry.list_all()

    def remove(self, name: str) -> bool:
        if not self._registry.remove(name):
            return False
        self._cache.remove_by_name(name)
        return True

    # ---- 构建执行编排 ----

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

        effective_ref = self._executor.resolve_ref(spec, repo_ref)
        cached = self._cache.check(spec, effective_ref, force)
        if cached is not None:
            return cached

        resolved_work_dir = self._executor.resolve_work_dir(spec, work_dir, repo_ref)
        if resolved_work_dir.startswith("ERROR:"):
            return BuildResult(
                spec=spec, status="failed",
                message=resolved_work_dir.removeprefix("ERROR:"), repo_ref=effective_ref,
            )
        result = self._executor.execute(spec, resolved_work_dir, env_vars, effective_ref)
        if result.status == "success":
            self._cache.put(spec.name, effective_ref, result)
        return result

    # ---- 委托: 缓存管理 ----

    def is_cached(self, name: str, repo_ref: str = "") -> bool:
        return self._cache.is_cached(name, repo_ref)

    def invalidate_cache(self, name: str, repo_ref: str = "") -> bool:
        return self._cache.invalidate(name, repo_ref)

    # ---- 委托: 清理 ----

    def clean(self, name: str, *, work_dir: str = "") -> bool:
        spec = self.get(name)
        if spec is None:
            return False
        success = self._executor.clean(spec, work_dir)
        if success:
            self.invalidate_cache(name)
        return success
