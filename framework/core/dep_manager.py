"""依赖包管理器

管理依赖包的本地版本切换、下载和缓存。

依赖包通常体积很大（EDA 工具、固件、模型库等），因此采用
"本地优先" 策略：

  1. local:  已安装在固定路径，通过 base_path/{version} 切换版本
  2. api:    从制品服务器 API 下载（本地不存在时才下载）
  3. lfs:    存储在本仓库 Git LFS 中
  4. url:    直接 URL 下载

核心逻辑:
  - 所有包都可配置 base_path 指定本地安装根目录
  - fetch() 先检查 base_path/version/ 是否存在，存在则直接返回
  - 仅当本地不存在时，才按 source 类型执行远程下载
  - resolve() 仅做本地查找，不触发下载
  - list_local_versions() 查看本地已安装的所有版本

用法:
    from framework.core.dep_manager import DepManager

    dm = DepManager()
    dm.fetch_all()
    dm.fetch("model_lib", version="v2.1.0")

    # 仅本地切换版本（不下载）
    path = dm.resolve("vcs", version="U-2023.03-SP2")

    # 查看本地已安装版本
    versions = dm.list_local_versions("vcs")
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from framework.utils.yaml_io import load_yaml

logger = logging.getLogger(__name__)

def _packages_dir() -> str:
    """获取包存储目录（统一走 Config）"""
    from framework.core.config import get_config
    return get_config().packages_dir


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


class DepManager:
    """依赖包统一管理器

    优先使用本地已安装版本（base_path/version/），
    仅当本地不存在时才按 source 类型执行远程拉取。
    """

    def __init__(
        self,
        registry_path: str = "",
        cache_dir: str = "",
    ) -> None:
        if not registry_path or not cache_dir:
            from framework.core.config import get_config
            cfg = get_config()
            registry_path = registry_path or cfg.manifest
            cache_dir = cache_dir or cfg.cache_dir
        self.registry_path = Path(registry_path)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.packages: dict[str, PackageInfo] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if not self.registry_path.exists():
            logger.warning("清单文件不存在: %s", self.registry_path)
            return

        data = load_yaml(self.registry_path)

        # 加载 eda_tools 段 —— 统一作为 local 类型的包
        for name, info in (data.get("eda_tools") or {}).items():
            if info is None:
                continue
            install_path = info.get("install_path", "")
            self.packages[name] = PackageInfo(
                name=name,
                owner=info.get("owner", "eda"),
                version=info.get("version", "latest"),
                source="local",
                description=info.get("description", f"EDA 工具 {name}"),
                base_path=install_path,
                env_vars=info.get("env_vars", {}),
            )

        # 加载 packages 段
        for name, info in (data.get("packages") or {}).items():
            if info is None:
                continue
            self.packages[name] = PackageInfo(
                name=name,
                owner=info.get("owner", "unknown"),
                version=info.get("version", "latest"),
                source=info.get("source", "api"),
                description=info.get("description", ""),
                base_path=info.get("base_path", ""),
                api_url=info.get("api_url", ""),
                url=info.get("url", ""),
                lfs_path=info.get("lfs_path", ""),
                checksum_sha256=info.get("checksum_sha256", ""),
                env_vars=info.get("env_vars", {}),
            )

        logger.info("已加载 %d 个依赖包", len(self.packages))

    # ------------------------------------------------------------------
    # 本地版本解析（不下载）
    # ------------------------------------------------------------------

    def resolve(self, name: str, version: str | None = None) -> Path | None:
        """解析本地已安装版本的路径，不触发任何下载。

        返回版本目录路径，若本地不存在则返回 None。
        """
        pkg = self.packages.get(name)
        if pkg is None:
            raise ValueError(
                f"依赖包 '{name}' 不在清单中。"
                f"可用: {list(self.packages.keys())}"
            )

        ver = version or pkg.version
        local_path = self._local_version_path(pkg, ver)
        if local_path and local_path.exists():
            logger.info("本地命中: %s@%s -> %s", name, ver, local_path)
            return local_path
        return None

    def _local_version_path(self, pkg: PackageInfo, version: str) -> Path | None:
        """计算包在本地的版本目录路径。

        路径规则:
          - 有 base_path: base_path/version/  （如 /opt/synopsys/vcs/U-2023.03-SP2/）
          - 无 base_path 但 source=lfs: deps/packages/<name>/<version>/
          - 其他: deps/cache/<name>/<version>/
        """
        if pkg.base_path:
            return Path(pkg.base_path) / version
        if pkg.source == "lfs":
            if pkg.lfs_path:
                return Path(pkg.lfs_path)
            return Path(_packages_dir()) / pkg.name / version
        # api/url 类型的缓存目录
        return self.cache_dir / pkg.name / version

    def list_local_versions(self, name: str) -> list[str]:
        """列出某个包在本地已安装的所有版本。

        基于 base_path 目录扫描子目录，每个子目录名视为一个版本。
        """
        pkg = self.packages.get(name)
        if pkg is None:
            raise ValueError(
                f"依赖包 '{name}' 不在清单中。"
                f"可用: {list(self.packages.keys())}"
            )

        if pkg.base_path:
            base = Path(pkg.base_path)
        elif pkg.source == "lfs":
            base = Path(_packages_dir()) / pkg.name
        else:
            base = self.cache_dir / pkg.name

        if not base.exists():
            return []

        return sorted(
            d.name for d in base.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )

    # ------------------------------------------------------------------
    # 拉取（本地优先 + 远程回退）
    # ------------------------------------------------------------------

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
        local_path = self._local_version_path(pkg, ver)
        if local_path and local_path.exists():
            logger.info(
                "本地版本已存在，直接使用: %s@%s -> %s", name, ver, local_path,
            )
            return local_path

        # ---- 2. 纯本地包不做远程下载 ----
        if pkg.source == "local":
            raise FileNotFoundError(
                f"本地包 '{name}' 版本 {ver} 不存在: {local_path}。"
                f"已安装版本: {self.list_local_versions(name)}"
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

    # ------------------------------------------------------------------
    # 远程下载
    # ------------------------------------------------------------------

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
            lfs_path = Path(_packages_dir()) / pkg.name / version
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

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_packages(self) -> list[dict[str, str]]:
        results = []
        for p in self.packages.values():
            info: dict[str, str] = {
                "name": p.name,
                "owner": p.owner,
                "version": p.version,
                "source": p.source,
                "description": p.description,
            }
            if p.base_path:
                info["base_path"] = p.base_path
            results.append(info)
        return results

    def get_env_vars(self, name: str, version: str | None = None) -> dict[str, str]:
        """获取包的环境变量，版本占位符 {version} 和 {path} 会被替换。"""
        pkg = self.packages.get(name)
        if pkg is None:
            return {}
        ver = version or pkg.version
        local_path = self._local_version_path(pkg, ver)
        result: dict[str, str] = {}
        for k, v in pkg.env_vars.items():
            val = v.replace("{version}", ver)
            if local_path:
                val = val.replace("{path}", str(local_path))
            result[k] = val
        return result

    # ------------------------------------------------------------------
    # LFS 上传
    # ------------------------------------------------------------------

    def upload_lfs(self, name: str, version: str, src_path: str) -> Path:
        """上传包到 Git LFS 存储"""
        src = Path(src_path)
        if not src.exists():
            raise FileNotFoundError(f"源文件不存在: {src_path}")

        dest_dir = Path(_packages_dir()) / name / version
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
