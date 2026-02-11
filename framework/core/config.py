"""集中配置管理

替代各模块散落的 DEFAULT_* 常量，提供统一的配置入口。
支持从 YAML 文件加载 + 编程式覆盖。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from framework.utils.yaml_io import load_yaml

logger = logging.getLogger(__name__)


@dataclass
class Config:
    """框架全局配置"""

    # 目录
    suite_dir: str = "testdata/configs"
    result_dir: str = "results"
    cache_dir: str = "deps/cache"
    history_file: str = "data/history.json"
    cases_file: str = "data/cases.yml"
    snapshots_dir: str = "deps/snapshots"
    manifest: str = "deps/manifest.yml"
    workspace_dir: str = "data/workspaces"
    storage_dir: str = "data/storage"
    log_rules_file: str = "configs/log_rules.yml"

    # 执行
    max_workers: int = 8
    default_timeout: int = 3600

    # 资源
    resource_mode: str = "self"
    resource_api_url: str = ""

    # 存储
    storage_backend: str = "local"
    storage_remote_url: str = ""
    storage_cache_days: int = 7

    # 自定义扩展 (放不到字段里的配置项)
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str = "configs/default.yml") -> Config:
        """从 YAML 文件加载配置，不存在则返回默认"""
        data = load_yaml(path)
        if not data:
            return cls()
        known = {f.name for f in cls.__dataclass_fields__.values()}
        matched = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        cfg = cls(**matched)
        cfg.extra = extra
        return cfg

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


# 全局单例，首次 import 时不加载文件；由 CLI / Web 入口显式初始化
_current: Config | None = None


def get_config() -> Config:
    """获取当前配置（未初始化则返回默认值）"""
    global _current  # noqa: PLW0603
    if _current is None:
        _current = Config()
    return _current


def init_config(path: str = "configs/default.yml") -> Config:
    """从文件初始化全局配置"""
    global _current  # noqa: PLW0603
    _current = Config.from_file(path)
    logger.info("配置已加载: %s", path)
    return _current
