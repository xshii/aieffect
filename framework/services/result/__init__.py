"""结果服务模块 - 模块化重构

拆分说明：
- storage.py: 结果存储 (~105 行)
- query.py: 结果查询 (~78 行)
- compare.py: 结果对比 (~89 行)
- uploader.py: 结果上传 + StorageConfig (~280 行)

总计从 464 行拆分为 4 个模块，平均每个模块 ~140 行
"""

from framework.services.result.compare import ResultCompare
from framework.services.result.query import ResultQuery
from framework.services.result.storage import ResultStorage
from framework.services.result.uploader import ResultUploader, StorageConfig

__all__ = [
    "ResultStorage",
    "ResultQuery",
    "ResultCompare",
    "ResultUploader",
    "StorageConfig",
]
