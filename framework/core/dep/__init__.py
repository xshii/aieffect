"""依赖包管理模块 - 模块化重构

拆分说明:
- models.py: 数据模型 (~29 行)
- registry.py: 注册表加载 (~93 行)
- resolver.py: 本地解析 (~114 行)
- fetcher.py: 远程拉取 (~222 行)

总计从 405 行拆分为 4 个模块
"""

from framework.core.dep.fetcher import PackageFetcher
from framework.core.dep.models import PackageInfo
from framework.core.dep.registry import PackageRegistry
from framework.core.dep.resolver import PackageResolver

__all__ = [
    "PackageInfo",
    "PackageRegistry",
    "PackageResolver",
    "PackageFetcher",
]
