"""代码仓 Checkout 协调器

职责：
- 协调 checkout 流程
- 管理工作空间缓存
- 执行 checkout 后的步骤（依赖、setup、build）
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.services.repo.registry import RepoRegistry
    from framework.services.repo.sources import ApiSource, GitSource, TarSource

from framework.core.exceptions import ValidationError
from framework.core.models import CaseRepoBinding, RepoSpec, RepoWorkspace
from framework.utils.shell import run_cmd

logger = logging.getLogger(__name__)


class RepoCheckout:
    """代码仓 Checkout 管理器"""

    def __init__(
        self,
        registry: RepoRegistry,
        workspace_root: str = "",
        git_source: GitSource | None = None,
        tar_source: TarSource | None = None,
        api_source: ApiSource | None = None,
    ) -> None:
        if not workspace_root:
            from framework.core.config import get_config
            workspace_root = get_config().workspace_dir
        self.registry = registry
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._workspace_cache: dict[tuple[str, str], RepoWorkspace] = {}

        # 初始化来源适配器
        if git_source is None:
            from framework.services.repo.sources import GitSource
            git_source = GitSource()
        if tar_source is None:
            from framework.services.repo.sources import TarSource
            tar_source = TarSource()
        if api_source is None:
            from framework.services.repo.sources import ApiSource
            api_source = ApiSource()

        self._git_source = git_source
        self._tar_source = tar_source
        self._api_source = api_source

    def checkout(self, name: str, *, ref_override: str = "", shared: bool = True) -> RepoWorkspace:
        """根据来源类型获取代码仓到本地工作目录

        shared=True 时，同 (name, ref) 的已有 checkout 直接复用。
        """
        spec = self.registry.get(name)
        if spec is None:
            raise ValidationError(f"代码仓未注册: {name}")

        ref = ref_override or spec.ref
        cache_key = (name, ref)

        # 复用已有工作目录
        if shared and cache_key in self._workspace_cache:
            cached = self._workspace_cache[cache_key]
            if cached.status not in ("error", "pending"):
                logger.info("复用已有工作目录: %s@%s -> %s", name, ref, cached.local_path)
                return cached

        ws = self._dispatch_checkout(spec, ref)
        self._post_checkout(ws, spec, name)
        self._workspace_cache[cache_key] = ws
        return ws

    def checkout_for_case(self, binding: CaseRepoBinding) -> RepoWorkspace:
        """按用例级绑定检出代码仓（支持分支覆盖 + 复用控制）"""
        return self.checkout(
            binding.repo_name,
            ref_override=binding.ref_override,
            shared=binding.shared,
        )

    def _dispatch_checkout(self, spec: RepoSpec, ref: str) -> RepoWorkspace:
        """按来源类型分派检出"""
        workspace = self._get_workspace_path(spec, ref)

        if spec.source_type == "git":
            return self._git_source.checkout(spec, ref, workspace)
        if spec.source_type == "tar":
            return self._tar_source.checkout(spec, ref, workspace)
        if spec.source_type == "api":
            return self._api_source.checkout(spec, ref, workspace)
        raise ValidationError(f"不支持的来源类型: {spec.source_type}")

    def _get_workspace_path(self, spec: RepoSpec, ref: str) -> Path:
        """计算工作空间路径"""
        if spec.source_type == "git":
            return self.workspace_root / spec.name / ref.replace("/", "_")
        # tar 和 api 使用默认路径
        return self.workspace_root / spec.name / (ref or "default")

    def _post_checkout(self, ws: RepoWorkspace, spec: RepoSpec, name: str) -> None:
        """检出后执行依赖解析和 setup/build 步骤"""
        if ws.status in ("error", "pending"):
            return
        if spec.deps:
            self._resolve_deps(spec.deps)
        cwd = Path(ws.local_path)
        if spec.path:
            cwd = cwd / spec.path
        if not cwd.exists():
            ws.status = "error"
            return
        try:
            if spec.setup_cmd:
                run_cmd(spec.setup_cmd, cwd=str(cwd), label="setup")
            if spec.build_cmd:
                run_cmd(spec.build_cmd, cwd=str(cwd), label="build")
            ws.local_path = str(cwd)
        except RuntimeError as e:
            ws.status = "error"
            logger.error("构建步骤失败 %s: %s", name, e)

    @staticmethod
    def _resolve_deps(dep_names: list[str]) -> None:
        """解析代码仓关联的依赖包"""
        try:
            from framework.core.dep_manager import DepManager
            dm = DepManager()
            for dep_name in dep_names:
                try:
                    dm.fetch(dep_name)
                    logger.info("  依赖就绪: %s", dep_name)
                except (OSError, ValueError, RuntimeError) as e:
                    logger.warning("  依赖获取失败（非致命）: %s - %s", dep_name, e)
        except (OSError, ValueError) as e:
            logger.warning("  依赖管理器初始化失败: %s", e)

    def clear_cache(self, name: str | None = None) -> None:
        """清理工作空间缓存"""
        if name is None:
            self._workspace_cache.clear()
        else:
            self._workspace_cache = {
                k: v for k, v in self._workspace_cache.items() if k[0] != name
            }
