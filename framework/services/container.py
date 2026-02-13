"""服务容器 — 统一依赖注入，消除跨服务/核心管理器的裸构造

所有服务和核心管理器通过容器获取，同一容器内的实例共享状态（缓存等）。
CLI 和 Web 层均应通过 get_container() 获取服务，而非直接 import 构造。

依赖关系图（→ 表示依赖）:
  build   → repo
  stimulus → repo
  其余服务均为独立实例

用法:
    container = ServiceContainer()
    build_svc = container.build          # 懒加载
    repo_svc  = container.repo           # 同容器共享

    # 全局单例（Web / 多模块共享）
    from framework.services.container import get_container
    svc = get_container().env
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.core.case_manager import CaseManager
    from framework.core.dep_manager import DepManager
    from framework.core.history import HistoryManager
    from framework.core.log_checker import LogChecker
    from framework.core.resource import ResourceManager
    from framework.core.snapshot import SnapshotManager
    from framework.services.build_service import BuildService
    from framework.services.env_service import EnvService
    from framework.services.repo_service import RepoService
    from framework.services.result_service import ResultService
    from framework.services.run_service import RunService
    from framework.services.stimulus_service import StimulusService

logger = logging.getLogger(__name__)


class ServiceContainer:
    """懒加载服务容器 — 每个实例持有一组共享的服务和核心管理器"""

    def __init__(self) -> None:
        self._instances: dict[str, object] = {}

    # ---- 服务层 ----

    @property
    def repo(self) -> RepoService:
        if "repo" not in self._instances:
            from framework.services.repo_service import RepoService
            self._instances["repo"] = RepoService()
        return self._instances["repo"]  # type: ignore[return-value]

    @property
    def build(self) -> BuildService:
        if "build" not in self._instances:
            from framework.services.build_service import BuildService
            self._instances["build"] = BuildService(repo_service=self.repo)
        return self._instances["build"]  # type: ignore[return-value]

    @property
    def stimulus(self) -> StimulusService:
        if "stimulus" not in self._instances:
            from framework.services.stimulus_service import StimulusService
            self._instances["stimulus"] = StimulusService(repo_service=self.repo)
        return self._instances["stimulus"]  # type: ignore[return-value]

    @property
    def env(self) -> EnvService:
        if "env" not in self._instances:
            from framework.services.env_service import EnvService
            self._instances["env"] = EnvService()
        return self._instances["env"]  # type: ignore[return-value]

    @property
    def result(self) -> ResultService:
        if "result" not in self._instances:
            from framework.services.result_service import ResultService
            self._instances["result"] = ResultService()
        return self._instances["result"]  # type: ignore[return-value]

    @property
    def run(self) -> RunService:
        if "run" not in self._instances:
            from framework.services.run_service import RunService
            self._instances["run"] = RunService()
        return self._instances["run"]  # type: ignore[return-value]

    # ---- 核心管理器（Facade — 统一访问入口） ----

    @property
    def cases(self) -> CaseManager:
        if "cases" not in self._instances:
            from framework.core.case_manager import CaseManager
            self._instances["cases"] = CaseManager()
        return self._instances["cases"]  # type: ignore[return-value]

    @property
    def deps(self) -> DepManager:
        if "deps" not in self._instances:
            from framework.core.dep_manager import DepManager
            self._instances["deps"] = DepManager()
        return self._instances["deps"]  # type: ignore[return-value]

    @property
    def history(self) -> HistoryManager:
        if "history" not in self._instances:
            from framework.core.history import HistoryManager
            self._instances["history"] = HistoryManager()
        return self._instances["history"]  # type: ignore[return-value]

    @property
    def snapshots(self) -> SnapshotManager:
        if "snapshots" not in self._instances:
            from framework.core.snapshot import SnapshotManager
            self._instances["snapshots"] = SnapshotManager()
        return self._instances["snapshots"]  # type: ignore[return-value]

    @property
    def resources(self) -> ResourceManager:
        if "resources" not in self._instances:
            from framework.core.resource import ResourceManager
            self._instances["resources"] = ResourceManager()
        return self._instances["resources"]  # type: ignore[return-value]

    @property
    def log_checker(self) -> LogChecker:
        if "log_checker" not in self._instances:
            from framework.core.log_checker import LogChecker
            self._instances["log_checker"] = LogChecker()
        return self._instances["log_checker"]  # type: ignore[return-value]


# ---- 全局单例 ----

_global: ServiceContainer | None = None
_global_lock = threading.Lock()


def get_container() -> ServiceContainer:
    """获取全局 ServiceContainer 单例（线程安全）"""
    global _global  # noqa: PLW0603
    if _global is not None:
        return _global
    with _global_lock:
        if _global is None:
            _global = ServiceContainer()
        return _global


def reset_container() -> None:
    """重置全局容器（仅用于测试）"""
    global _global  # noqa: PLW0603
    with _global_lock:
        _global = None
