"""激励服务模块 - 模块化重构

拆分说明：
- registry.py: 激励源 CRUD（~95 行）
- constructor.py: 激励获取与构造（~250 行）
- result_stimulus.py: 结果激励管理（~190 行）
- trigger.py: 触发器管理（~190 行）

总计从 585 行拆分为 4 个模块，平均每个模块 ~180 行
"""

from framework.services.stimulus.constructor import StimulusConstructor
from framework.services.stimulus.registry import StimulusRegistry
from framework.services.stimulus.result_stimulus import ResultStimulusManager
from framework.services.stimulus.trigger import TriggerManager

__all__ = [
    "StimulusRegistry",
    "StimulusConstructor",
    "ResultStimulusManager",
    "TriggerManager",
]
