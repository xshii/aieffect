"""服务容器 — 统一依赖注入，消除跨服务/核心管理器的裸构造

所有服务和核心管理器通过容器获取，同一容器内的实例共享状态（缓存等）。
CLI 和 Web 层均应通过 get_container() 获取服务，而非直接 import 构造。

依赖关系图（→ 表示依赖）:
  build   → repo
  stimulus → repo
  其余服务均为独立实例

Config 注入:
  容器接受可选 Config 参数，将配置显式传递给各服务/管理器。
  若不提供，则使用全局 get_config() 作为后备（向后兼容）。

用法:
    container = ServiceContainer()
    build_svc = container.build          # 懒加载
    repo_svc  = container.repo           # 同容器共享

    # 显式注入配置
    cfg = Config.from_file("my_config.yml")
    container = ServiceContainer(config=cfg)

    # 全局单例（Web / 多模块共享）
    from framework.services.container import get_container
    svc = get_container().env
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.core.case_manager import CaseManager
    from framework.core.config import Config
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
    """懒加载服务容器 — 每个实例持有一组共享的服务和核心管理器

    接受可选 Config，将配置显式传递给各服务，消除隐式 get_config() 调用。
    """

    def __init__(self, config: Config | None = None) -> None:
        self._instances: dict[str, object] = {}
        if config is None:
            from framework.core.config import get_config
            config = get_config()
        self._config = config

    @property
    def config(self) -> Config:
        return self._config

    # ---- 服务层 ----

    @property
    def repo(self) -> RepoService:
        if "repo" not in self._instances:
            from framework.services.repo_service import RepoService
            self._instances["repo"] = RepoService(
                registry_file=self._config.repos_file,
                workspace_root=self._config.workspace_dir,
            )
        return self._instances["repo"]  # type: ignore[return-value]

    @property
    def build(self) -> BuildService:
        if "build" not in self._instances:
            from framework.services.build_service import BuildService
            self._instances["build"] = BuildService(
                registry_file=self._config.builds_file,
                output_root=str(Path(self._config.workspace_dir) / "builds"),
                repo_service=self.repo,
            )
        return self._instances["build"]  # type: ignore[return-value]

    @property
    def stimulus(self) -> StimulusService:
        if "stimulus" not in self._instances:
            from framework.services.stimulus_service import StimulusService
            self._instances["stimulus"] = StimulusService(
                registry_file=self._config.stimuli_file,
                artifact_dir=str(Path(self._config.workspace_dir) / "stimuli"),
                repo_service=self.repo,
            )
        return self._instances["stimulus"]  # type: ignore[return-value]

    @property
    def env(self) -> EnvService:
        if "env" not in self._instances:
            from framework.services.env_service import EnvService
            self._instances["env"] = EnvService(
                registry_file=self._config.envs_file,
            )
        return self._instances["env"]  # type: ignore[return-value]

    @property
    def result(self) -> ResultService:
        if "result" not in self._instances:
            from framework.services.result_service import ResultService
            self._instances["result"] = ResultService(
                result_dir=self._config.result_dir,
                history_file=self._config.history_file,
            )
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
            self._instances["cases"] = CaseManager(
                cases_file=self._config.cases_file,
            )
        return self._instances["cases"]  # type: ignore[return-value]

    @property
    def deps(self) -> DepManager:
        if "deps" not in self._instances:
            from framework.core.dep_manager import DepManager
            self._instances["deps"] = DepManager(
                registry_path=self._config.manifest,
                cache_dir=self._config.cache_dir,
            )
        return self._instances["deps"]  # type: ignore[return-value]

    @property
    def history(self) -> HistoryManager:
        if "history" not in self._instances:
            from framework.core.history import HistoryManager
            self._instances["history"] = HistoryManager(
                history_file=self._config.history_file,
            )
        return self._instances["history"]  # type: ignore[return-value]

    @property
    def snapshots(self) -> SnapshotManager:
        if "snapshots" not in self._instances:
            from framework.core.snapshot import SnapshotManager
            self._instances["snapshots"] = SnapshotManager(
                manifest_path=self._config.manifest,
                snapshots_dir=self._config.snapshots_dir,
            )
        return self._instances["snapshots"]  # type: ignore[return-value]

    @property
    def resources(self) -> ResourceManager:
        if "resources" not in self._instances:
            from framework.core.resource import ResourceManager
            self._instances["resources"] = ResourceManager(
                mode=self._config.resource_mode,
                capacity=self._config.max_workers,
                api_url=self._config.resource_api_url,
            )
        return self._instances["resources"]  # type: ignore[return-value]

    @property
    def log_checker(self) -> LogChecker:
        if "log_checker" not in self._instances:
            from framework.core.log_checker import LogChecker
            self._instances["log_checker"] = LogChecker(
                rules_file=self._config.log_rules_file,
            )
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
