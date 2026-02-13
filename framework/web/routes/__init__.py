"""Web 路由模块 - Blueprint 集合

拆分说明:
- core_bp.py: 核心 API (3 routes)
- cases_bp.py: 用例管理 (5 routes)
- snapshots_bp.py: 快照管理 (4 routes)
- history_bp.py: 历史记录 (3 routes)
- utils_bp.py: 工具 API (5 routes)
- results_bp.py: 结果增强 (3 routes)
- orchestrate_bp.py: 编排执行 (1 route)

总计 7 个 Blueprint，24 个路由
"""

from framework.web.routes.cases_bp import cases_bp
from framework.web.routes.core_bp import core_bp
from framework.web.routes.history_bp import history_bp
from framework.web.routes.orchestrate_bp import orchestrate_bp
from framework.web.routes.results_bp import results_bp
from framework.web.routes.snapshots_bp import snapshots_bp
from framework.web.routes.utils_bp import utils_bp

__all__ = [
    "core_bp",
    "cases_bp",
    "snapshots_bp",
    "history_bp",
    "utils_bp",
    "results_bp",
    "orchestrate_bp",
]
