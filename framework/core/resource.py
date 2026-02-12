"""资源繁忙度管理

两种模式：
  - self: 框架自管理，跟踪本地正在执行的任务数 / worker 占用
  - api:  通过外部 API 查询资源占用情况

支持 API 查询当前资源状态，供调度器在执行前检查资源是否充足。
"""

from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from json import JSONDecodeError
from json import loads as json_loads

logger = logging.getLogger(__name__)


@dataclass
class ResourceStatus:
    """资源状态快照"""

    capacity: int = 0       # 总容量
    in_use: int = 0         # 使用中
    available: int = 0      # 可用
    tasks: list[str] = field(default_factory=list)  # 当前运行中的任务名
    timestamp: float = 0.0


class ResourceManager:
    """资源繁忙度管理器"""

    def __init__(self, mode: str = "self", capacity: int = 8, api_url: str = "") -> None:
        """
        参数:
            mode: "self"（自管理）或 "api"（外部 API 查询）
            capacity: 自管理模式下的最大容量
            api_url: API 模式下的查询地址
        """
        if mode == "api" and api_url:
            from framework.utils.net import validate_url_scheme
            validate_url_scheme(api_url, context="ResourceManager api_url")
        self.mode = mode
        self.capacity = max(1, capacity)
        self.api_url = api_url

        # 自管理状态
        self._lock = threading.Lock()
        self._in_use = 0
        self._tasks: list[str] = []

    def acquire(self, task_name: str = "") -> bool:
        """尝试获取一个资源槽位，返回是否成功"""
        if self.mode == "api":
            status = self.status()
            return status.available > 0

        with self._lock:
            if self._in_use >= self.capacity:
                logger.warning("资源不足: %d/%d 已占用", self._in_use, self.capacity)
                return False
            self._in_use += 1
            if task_name:
                self._tasks.append(task_name)
            logger.info("资源已分配: %s (%d/%d)", task_name, self._in_use, self.capacity)
            return True

    def release(self, task_name: str = "") -> None:
        """释放一个资源槽位"""
        if self.mode == "api":
            return

        with self._lock:
            self._in_use = max(0, self._in_use - 1)
            if task_name and task_name in self._tasks:
                self._tasks.remove(task_name)
            logger.info("资源已释放: %s (%d/%d)", task_name, self._in_use, self.capacity)

    def status(self) -> ResourceStatus:
        """查询当前资源状态"""
        if self.mode == "api":
            return self._query_api()

        with self._lock:
            return ResourceStatus(
                capacity=self.capacity,
                in_use=self._in_use,
                available=self.capacity - self._in_use,
                tasks=list(self._tasks),
                timestamp=time.time(),
            )

    def _query_api(self) -> ResourceStatus:
        """通过外部 API 查询资源状态"""
        if not self.api_url:
            logger.warning("API 模式但未配置 api_url")
            return ResourceStatus(timestamp=time.time())

        try:
            with urllib.request.urlopen(self.api_url, timeout=10) as resp:  # nosec B310
                data = json_loads(resp.read().decode())
            return ResourceStatus(
                capacity=data.get("capacity", 0),
                in_use=data.get("in_use", 0),
                available=data.get("available", 0),
                tasks=data.get("tasks", []),
                timestamp=time.time(),
            )
        except (urllib.error.URLError, OSError, JSONDecodeError, KeyError) as e:
            logger.error("查询资源 API 失败: %s", e)
            return ResourceStatus(timestamp=time.time())
