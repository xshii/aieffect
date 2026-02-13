"""依赖包数据模型

数据类:
- PackageInfo: 包元信息
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_PACKAGES_DIR = "deps/packages"


@dataclass
class PackageInfo:
    """单个依赖包的元信息"""

    name: str
    owner: str
    version: str
    source: str  # "local", "api", "lfs", "url"
    description: str = ""
    base_path: str = ""       # 本地安装根目录，如 /opt/synopsys/vcs
    api_url: str = ""
    url: str = ""
    lfs_path: str = ""
    checksum_sha256: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)  # 环境变量模板
