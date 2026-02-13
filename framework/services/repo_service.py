"""代码仓服务 - 门面类（Facade Pattern）

职责：
- 统一对外接口，整合所有代码仓管理功能
- 保持向后兼容性
- 代理到各个子模块

重构说明：
- 原 382 行单体类拆分为 4 个模块
- 使用策略模式处理不同来源
- 降低复杂度，提高可维护性
"""

from __future__ import annotations

from typing import Any

from framework.core.models import CaseRepoBinding, RepoSpec, RepoWorkspace
from framework.services.repo import (
    ApiSource,
    GitSource,
    RepoCheckout,
    RepoRegistry,
    TarSource,
    WorkspaceManager,
)


class RepoService(RepoRegistry):
    """代码仓生命周期管理 - 门面类

    整合 4 大能力:
      1. 注册管理: register, get, list_all, remove
      2. Checkout: checkout, checkout_for_case
      3. 多来源支持: Git / Tar / API
      4. 工作空间: list_workspaces, clean
    """

    def __init__(self, registry_file: str = "", workspace_root: str = "") -> None:
        super().__init__(registry_file)

        # 初始化来源适配器
        git_source = GitSource()
        tar_source = TarSource()
        api_source = ApiSource()

        # 初始化 checkout 管理器
        self._checkout = RepoCheckout(
            registry=self,
            workspace_root=workspace_root,
            git_source=git_source,
            tar_source=tar_source,
            api_source=api_source,
        )

        # 初始化工作空间管理器
        self._workspace = WorkspaceManager(
            workspace_root=workspace_root,
            checkout=self._checkout,
        )

        # 保留属性用于向后兼容
        self.workspace_root = self._checkout.workspace_root

    # =====================================================================
    # 1. 注册管理（继承自 RepoRegistry）
    # =====================================================================
    # register(), get(), list_all(), remove() 已由父类 RepoRegistry 提供

    # =====================================================================
    # 2. Checkout 操作（代理到 RepoCheckout）
    # =====================================================================

    def checkout(self, name: str, *, ref_override: str = "", shared: bool = True) -> RepoWorkspace:
        """根据来源类型获取代码仓到本地工作目录"""
        return self._checkout.checkout(name, ref_override=ref_override, shared=shared)

    def checkout_for_case(self, binding: CaseRepoBinding) -> RepoWorkspace:
        """按用例级绑定检出代码仓（支持分支覆盖 + 复用控制）"""
        return self._checkout.checkout_for_case(binding)

    # =====================================================================
    # 3. 工作空间管理（代理到 WorkspaceManager）
    # =====================================================================

    def list_workspaces(self) -> list[dict[str, str]]:
        """列出本地已检出的工作目录"""
        return self._workspace.list_workspaces()

    def clean(self, name: str) -> int:
        """清理代码仓本地工作目录，返回清理的目录数"""
        return self._workspace.clean(name)
