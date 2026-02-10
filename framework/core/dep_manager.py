"""依赖包管理器

管理从以下来源下载、验证和缓存依赖包：
  - api:  从制品服务器 API 下载（各组件团队各自发布）
  - lfs:  存储在本仓库 Git LFS 中（手动上传）
  - url:  直接 URL 下载

用法:
    from framework.core.dep_manager import DepManager

    dm = DepManager()
    dm.fetch_all()
    dm.fetch("model_lib", version="v2.1.0")
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

DEFAULT_REGISTRY = "deps/manifest.yml"
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
        if not self.registry_path.exists():
            logger.warning("清单文件不存在: %s", self.registry_path)
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

        logger.info("已加载 %d 个依赖包", len(self.packages))

    def fetch(self, name: str, version: str | None = None) -> Path:
        """拉取单个依赖包，返回本地路径"""
        pkg = self.packages.get(name)
        if pkg is None:
            raise ValueError(f"依赖包 '{name}' 不在清单中。可用: {list(self.packages.keys())}")

        ver = version or pkg.version
        logger.info("拉取 %s@%s (source=%s)", name, ver, pkg.source)

        if pkg.source == "lfs":
            dest = self._resolve_lfs(pkg, ver)
        else:
            dest = self._download(pkg, ver)

        if pkg.checksum_sha256 and dest.is_file():
            self._verify_checksum(dest, pkg.checksum_sha256)

        return dest

    def fetch_all(self) -> dict[str, Path]:
        """拉取清单中的全部包"""
        results = {}
        for name in self.packages:
            try:
                results[name] = self.fetch(name)
            except Exception:
                logger.exception("拉取失败: %s", name)
        return results

    def _download(self, pkg: PackageInfo, version: str) -> Path:
        """统一下载逻辑（api / url 共用）"""
        if pkg.source == "api":
            if not pkg.api_url:
                raise ValueError(f"依赖包 '{pkg.name}' 未定义 api_url")
            download_url = f"{pkg.api_url.rstrip('/')}/{version}/{pkg.name}.tar.gz"
            filename = f"{pkg.name}.tar.gz"
        elif pkg.source == "url":
            if not pkg.url:
                raise ValueError(f"依赖包 '{pkg.name}' 未定义 url")
            download_url = pkg.url.replace("{version}", version)
            filename = download_url.rstrip("/").split("/")[-1]
            if not filename:
                raise ValueError(f"无法从 URL 解析文件名: {download_url}")
        else:
            raise ValueError(f"不支持的来源类型: {pkg.source}")

        dest = self.cache_dir / pkg.name / version / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            logger.info("  缓存命中: %s", dest)
            return dest

        logger.info("  下载: %s", download_url)
        try:
            urllib.request.urlretrieve(download_url, str(dest))
        except urllib.error.HTTPError as e:
            dest.unlink(missing_ok=True)
            raise ConnectionError(f"下载失败 (HTTP {e.code}): {download_url}") from e
        except urllib.error.URLError as e:
            dest.unlink(missing_ok=True)
            raise ConnectionError(f"网络错误: {download_url} - {e.reason}") from e
        except OSError as e:
            dest.unlink(missing_ok=True)
            raise ConnectionError(f"下载 I/O 错误: {download_url} - {e}") from e
        logger.info("  已保存: %s", dest)
        return dest

    def _resolve_lfs(self, pkg: PackageInfo, version: str) -> Path:
        """解析 Git LFS 包"""
        lfs_path = Path(pkg.lfs_path) if pkg.lfs_path else Path(DEFAULT_PACKAGES_DIR) / pkg.name / version
        if not lfs_path.exists():
            logger.info("  执行 git lfs pull: %s", lfs_path)
            subprocess.run(["git", "lfs", "pull", "--include", str(lfs_path)], check=False, capture_output=True)

        if not lfs_path.exists():
            raise FileNotFoundError(f"LFS 包未找到: {lfs_path}")

        logger.info("  LFS 已解析: %s", lfs_path)
        return lfs_path

    def _verify_checksum(self, path: Path, expected: str) -> None:
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual = sha256.hexdigest()
        if actual != expected:
            raise ValueError(f"校验和不匹配 {path}: 期望 {expected}, 实际 {actual}")
        logger.info("  校验和通过: %s", path.name)

    def list_packages(self) -> list[dict[str, str]]:
        return [
            {"name": p.name, "owner": p.owner, "version": p.version, "source": p.source, "description": p.description}
            for p in self.packages.values()
        ]

    def upload_lfs(self, name: str, version: str, src_path: str) -> Path:
        """上传包到 Git LFS 存储"""
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"源文件不存在: {src_path}")

        dest_dir = Path(DEFAULT_PACKAGES_DIR) / name / version
        dest_dir.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            dest = dest_dir
            shutil.copytree(src, dest, dirs_exist_ok=True)
        else:
            dest = dest_dir / src.name
            shutil.copy2(src, dest)

        subprocess.run(["git", "lfs", "track", f"deps/packages/{name}/**"], check=False, capture_output=True)
        logger.info("已上传 %s@%s -> %s", name, version, dest)
        return dest
