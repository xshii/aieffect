"""构建缓存管理

职责:
- 构建结果缓存
- 缓存命中检查
- 缓存失效管理

缓存策略:
  - 以 (build_name, repo_ref) 为缓存键
  - 同名同分支不重复构建
  - 指定新分支时自动重新构建
"""

from __future__ import annotations

import logging

from framework.core.models import BuildResult, BuildSpec

logger = logging.getLogger(__name__)


class BuildCache:
    """构建缓存管理器"""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, str], BuildResult] = {}

    def check(self, spec: BuildSpec, ref: str, force: bool) -> BuildResult | None:
        """检查构建缓存，返回缓存结果或None（未命中或force=True）"""
        cache_key = (spec.name, ref)
        if force or cache_key not in self._cache:
            return None
        cached = self._cache[cache_key]
        if cached.status != "success":
            return None
        logger.info("构建缓存命中: %s (ref=%s)", spec.name, ref)
        return BuildResult(
            spec=spec, output_path=cached.output_path,
            status="cached", duration=cached.duration,
            message=f"缓存命中 (ref={ref})",
            repo_ref=ref, cached=True,
        )

    def put(self, name: str, ref: str, result: BuildResult) -> None:
        """缓存构建结果"""
        self._cache[(name, ref)] = result

    def is_cached(self, name: str, repo_ref: str = "") -> bool:
        """检查缓存状态"""
        cached = self._cache.get((name, repo_ref))
        return cached is not None and cached.status == "success"

    def invalidate(self, name: str, repo_ref: str = "") -> bool:
        """清除缓存"""
        if repo_ref:
            key = (name, repo_ref)
            if key in self._cache:
                del self._cache[key]
                return True
            return False
        keys = [k for k in self._cache if k[0] == name]
        for k in keys:
            del self._cache[k]
        return len(keys) > 0

    def remove_by_name(self, name: str) -> None:
        """删除指定构建的所有缓存"""
        keys_to_remove = [k for k in self._cache if k[0] == name]
        for k in keys_to_remove:
            del self._cache[k]
