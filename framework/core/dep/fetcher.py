"""依赖包拉取器

职责:
- 拉取依赖包（本地优先 + 远程回退）
- API/URL 下载
- Git LFS 解析
- 校验和验证
- LFS 上传
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from framework.core.dep.resolver import PackageResolver

from framework.core.dep.models import DEFAULT_PACKAGES_DIR, PackageInfo

logger = logging.getLogger(__name__)


class PackageFetcher:
    """依赖包拉取器 - 本地优先 + 远程下载"""

    def __init__(
        self,
        packages: dict[str, PackageInfo],
        cache_dir: Path,
        resolver: PackageResolver,
    ) -> None:
        self.packages = packages
        self.cache_dir = cache_dir
        self.resolver = resolver

    def fetch(self, name: str, version: str | None = None) -> Path:
        """拉取单个依赖包，返回本地路径。

        策略: 本地优先
          1. 检查本地是否已存在该版本 → 直接返回
          2. 不存在则按 source 类型远程拉取
        """
        pkg = self.packages.get(name)
        if pkg is None:
            raise ValueError(
                f"依赖包 '{name}' 不在清单中。"
                f"可用: {list(self.packages.keys())}"
            )

        ver = version or pkg.version

        # ---- 1. 本地优先检查 ----
        local_path = self.resolver.local_version_path(pkg, ver)
        if local_path and local_path.exists():
            logger.info(
                "本地版本已存在，直接使用: %s@%s -> %s", name, ver, local_path,
            )
            return local_path

        # ---- 2. 纯本地包不做远程下载 ----
        if pkg.source == "local":
            raise FileNotFoundError(
                f"本地包 '{name}' 版本 {ver} 不存在: {local_path}。"
                f"已安装版本: {self.resolver.list_local_versions(name)}"
            )

        logger.info("本地不存在，远程拉取: %s@%s (source=%s)", name, ver, pkg.source)

        # ---- 3. 远程拉取 ----
        if pkg.source == "lfs":
            dest = self._resolve_lfs(pkg, ver)
        else:
            dest = self._download(pkg, ver)

        if pkg.checksum_sha256 and dest.is_file():
            self._verify_checksum(dest, pkg.checksum_sha256)

        return dest

    def fetch_all(self) -> dict[str, Path | str]:
        """拉取清单中的全部包，返回 {name: path|error_msg}"""
        results: dict[str, Path | str] = {}
        failed: dict[str, str] = {}
        for name in self.packages:
            try:
                results[name] = self.fetch(name)
            except (OSError, ValueError, ConnectionError) as exc:
                logger.exception("拉取失败: %s", name)
                failed[name] = str(exc)
                results[name] = f"[FAILED] {exc}"
        if failed:
            logger.warning(
                "拉取汇总: %d 成功, %d 失败 (%s)",
                len(results) - len(failed),
                len(failed),
                ", ".join(failed),
            )
        return results

    def _download(self, pkg: PackageInfo, version: str) -> Path:
        """统一下载逻辑（api / url 共用）"""
        if pkg.source == "api":
            if not pkg.api_url:
                raise ValueError(f"依赖包 '{pkg.name}' 未定义 api_url")
            download_url = (
                f"{pkg.api_url.rstrip('/')}/{version}/{pkg.name}.tar.gz"
            )
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

        # 下载到 base_path/version/ 或 cache_dir/name/version/
        if pkg.base_path:
            dest_dir = Path(pkg.base_path) / version
        else:
            dest_dir = self.cache_dir / pkg.name / version
        dest = dest_dir / filename
        dest.parent.mkdir(parents=True, exist_ok=True)

        if dest.exists():
            logger.info("  缓存命中: %s", dest)
            return dest

        logger.info("  下载: %s", download_url)
        from framework.utils.net import validate_url_scheme
        validate_url_scheme(download_url, context=f"dep download {pkg.name}")
        try:
            urllib.request.urlretrieve(download_url, str(dest))  # nosec B310
        except (urllib.error.HTTPError, urllib.error.URLError, OSError) as e:
            dest.unlink(missing_ok=True)
            raise ConnectionError(f"下载失败: {download_url} - {e}") from e
        logger.info("  已保存: %s", dest)
        return dest

    def _resolve_lfs(self, pkg: PackageInfo, version: str) -> Path:
        """解析 Git LFS 包"""
        if pkg.lfs_path:
            lfs_path = Path(pkg.lfs_path)
        else:
            lfs_path = Path(DEFAULT_PACKAGES_DIR) / pkg.name / version
        if not lfs_path.exists():
            logger.info("  执行 git lfs pull: %s", lfs_path)
            subprocess.run(
                ["git", "lfs", "pull", "--include", str(lfs_path)],
                check=False, capture_output=True,
            )

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
            raise ValueError(
                f"校验和不匹配 {path}: 期望 {expected}, 实际 {actual}",
            )
        logger.info("  校验和通过: %s", path.name)

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

        subprocess.run(
            ["git", "lfs", "track", f"deps/packages/{name}/**"],
            check=False, capture_output=True,
        )
        logger.info("已上传 %s@%s -> %s", name, version, dest)
        return dest
