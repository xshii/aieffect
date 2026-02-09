"""依赖包管理器

管理从以下来源下载、验证和缓存依赖包：
  - api:  从制品服务器 API 下载（各组件团队各自发布）
  - lfs:  存储在本仓库 Git LFS 中（手动上传）
  - url:  直接 URL 下载

用法:
    from framework.core.dep_manager import DepManager

    dm = DepManager(registry_path="deps/registry.yml")
    dm.fetch_all()                    # 下载全部依赖
    dm.fetch("model_lib")             # 下载指定依赖
    dm.fetch("model_lib", version="v2.1.0")  # 指定版本下载
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY = "deps/registry.yml"
DEFAULT_CACHE_DIR = "deps/cache"
DEFAULT_PACKAGES_DIR = "deps/packages"


@dataclass
class PackageInfo:
    """单个依赖包的元信息"""

    name: str
    owner: str
    version: str
    source: str  # "api", "lfs", "url"
    description: str = ""
    api_url: str = ""
    url: str = ""
    lfs_path: str = ""
    checksum_sha256: str = ""


class DepManager:
    """依赖包统一管理器"""

    def __init__(
        self,
        registry_path: str = DEFAULT_REGISTRY,
        cache_dir: str = DEFAULT_CACHE_DIR,
    ) -> None:
        self.registry_path = Path(registry_path)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.packages: dict[str, PackageInfo] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        """从 YAML 加载包注册表"""
        if not self.registry_path.exists():
            logger.warning("Registry not found: %s", self.registry_path)
            return

        with open(self.registry_path) as f:
            data = yaml.safe_load(f) or {}

        for name, info in (data.get("packages") or {}).items():
            if info is None:
                continue
            self.packages[name] = PackageInfo(
                name=name,
                owner=info.get("owner", "unknown"),
                version=info.get("version", "latest"),
                source=info.get("source", "api"),
                description=info.get("description", ""),
                api_url=info.get("api_url", ""),
                url=info.get("url", ""),
                lfs_path=info.get("lfs_path", ""),
                checksum_sha256=info.get("checksum_sha256", ""),
            )

        logger.info("Loaded %d packages from registry", len(self.packages))

    def fetch(self, name: str, version: str | None = None) -> Path:
        """拉取单个依赖包

        参数:
            name: 包名（须在注册表中存在）
            version: 覆盖版本（None 则使用注册表默认版本）

        返回:
            缓存中的包路径
        """
        pkg = self.packages.get(name)
        if pkg is None:
            raise ValueError(f"Package '{name}' not found in registry. Available: {list(self.packages.keys())}")

        effective_version = version or pkg.version
        logger.info("Fetching %s@%s (source=%s, owner=%s)", name, effective_version, pkg.source, pkg.owner)

        fetchers = {
            "api": self._fetch_api,
            "lfs": self._fetch_lfs,
            "url": self._fetch_url,
        }

        fetcher = fetchers.get(pkg.source)
        if fetcher is None:
            raise ValueError(f"Unknown source type '{pkg.source}' for package '{name}'")

        dest = fetcher(pkg, effective_version)

        # 如有校验和则验证
        if pkg.checksum_sha256 and dest.is_file():
            self._verify_checksum(dest, pkg.checksum_sha256)

        return dest

    def fetch_all(self) -> dict[str, Path]:
        """拉取注册表中的全部包"""
        results = {}
        for name in self.packages:
            try:
                results[name] = self.fetch(name)
            except Exception:
                logger.exception("Failed to fetch %s", name)
        return results

    def _fetch_api(self, pkg: PackageInfo, version: str) -> Path:
        """从制品服务器 API 下载包"""
        if not pkg.api_url:
            raise ValueError(f"No api_url defined for package '{pkg.name}'")

        # 构造带版本的下载 URL: {api_url}/{version}/{name}.tar.gz
        download_url = f"{pkg.api_url.rstrip('/')}/{version}/{pkg.name}.tar.gz"
        dest = self.cache_dir / pkg.name / version / f"{pkg.name}.tar.gz"
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            logger.info("  Cache hit: %s", dest)
            return dest

        logger.info("  Downloading: %s", download_url)
        urllib.request.urlretrieve(download_url, str(dest))
        logger.info("  Saved to: %s", dest)
        return dest

    def _fetch_lfs(self, pkg: PackageInfo, version: str) -> Path:
        """解析 Git LFS 包（已在仓库中）"""
        lfs_path = Path(pkg.lfs_path) if pkg.lfs_path else Path(DEFAULT_PACKAGES_DIR) / pkg.name / version
        if not lfs_path.exists():
            # 尝试 git lfs pull 拉取指定路径
            logger.info("  Running git lfs pull for: %s", lfs_path)
            subprocess.run(
                ["git", "lfs", "pull", "--include", str(lfs_path)],
                check=False,
                capture_output=True,
            )

        if not lfs_path.exists():
            raise FileNotFoundError(f"LFS package not found: {lfs_path}")

        logger.info("  LFS resolved: %s", lfs_path)
        return lfs_path

    def _fetch_url(self, pkg: PackageInfo, version: str) -> Path:
        """通过直接 URL 下载"""
        if not pkg.url:
            raise ValueError(f"No url defined for package '{pkg.name}'")

        url = pkg.url.replace("{version}", version)
        filename = url.split("/")[-1]
        dest = self.cache_dir / pkg.name / version / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            logger.info("  Cache hit: %s", dest)
            return dest

        logger.info("  Downloading: %s", url)
        urllib.request.urlretrieve(url, str(dest))
        logger.info("  Saved to: %s", dest)
        return dest

    def _verify_checksum(self, path: Path, expected: str) -> None:
        """验证下载文件的 SHA256 校验和"""
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual = sha256.hexdigest()
        if actual != expected:
            raise ValueError(f"Checksum mismatch for {path}: expected {expected}, got {actual}")
        logger.info("  Checksum OK: %s", path.name)

    def list_packages(self) -> list[dict[str, str]]:
        """列出所有已注册包的信息"""
        return [
            {
                "name": p.name,
                "owner": p.owner,
                "version": p.version,
                "source": p.source,
                "description": p.description,
            }
            for p in self.packages.values()
        ]

    def upload_lfs(self, name: str, version: str, src_path: str) -> Path:
        """上传包到 Git LFS 存储

        将文件复制到 deps/packages/<name>/<version>/ 并设置 LFS 追踪。

        参数:
            name: 包名
            version: 版本号
            src_path: 要上传的文件或目录路径

        返回:
            LFS 追踪的包路径
        """
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"Source not found: {src_path}")

        dest_dir = Path(DEFAULT_PACKAGES_DIR) / name / version
        dest_dir.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            dest = dest_dir
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            dest = dest_dir / src.name
            shutil.copy2(src, dest)

        # 确保 LFS 追踪规则存在
        lfs_pattern = f"deps/packages/{name}/**"
        subprocess.run(["git", "lfs", "track", lfs_pattern], check=False, capture_output=True)

        logger.info("Uploaded %s@%s to LFS: %s", name, version, dest)
        return dest
