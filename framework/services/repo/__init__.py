"""代码仓服务模块 - 模块化重构

拆分说明：
- registry.py: 代码仓 CRUD (~95 行)
- sources.py: 来源适配器 Git/Tar/API (~195 行)
- checkout.py: Checkout 协调器 (~155 行)
- workspace.py: 工作空间管理 (~80 行)

总计从 382 行拆分为 4 个模块，采用策略模式和依赖注入
"""

from framework.services.repo.checkout import RepoCheckout
from framework.services.repo.registry import RepoRegistry
from framework.services.repo.sources import ApiSource, GitSource, TarSource
from framework.services.repo.workspace import WorkspaceManager

__all__ = [
    "RepoRegistry",
    "RepoCheckout",
    "GitSource",
    "TarSource",
    "ApiSource",
    "WorkspaceManager",
]
