"""代码仓服务 — 多来源仓库注册 / 获取 / 复用 / 清理

支持三种来源:
  - git: Git 仓库 clone/fetch
  - tar: tar 包（本地或远程）解压
  - api: 通过 API 下载链接获取

支持:
  - 用例级分支覆盖（CaseRepoBinding.ref_override）
  - 跨用例工作目录复用（同 name+ref 共享 checkout）
  - 代码仓关联依赖包（deps 字段 → DepManager.fetch）
"""

from __future__ import annotations

import logging
import re
import subprocess
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

from framework.core.exceptions import ValidationError
from framework.core.models import CaseRepoBinding, RepoSpec, RepoWorkspace
from framework.core.registry import YamlRegistry
from framework.utils.shell import run_cmd

logger = logging.getLogger(__name__)

_SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9_./@\-]+$")


class RepoService(YamlRegistry):
    """代码仓生命周期管理"""

    section_key = "repos"

    def __init__(self, registry_file: str = "", workspace_root: str = "") -> None:
        if not registry_file:
            from framework.core.config import get_config
            registry_file = getattr(get_config(), "repos_file", "data/repos.yml")
        if not workspace_root:
            from framework.core.config import get_config
            workspace_root = get_config().workspace_dir
        super().__init__(registry_file)
        self.workspace_root = Path(workspace_root)
        self.workspace_root.mkdir(parents=True, exist_ok=True)
        self._workspace_cache: dict[tuple[str, str], RepoWorkspace] = {}

    # ---- 注册 / CRUD ----

    def register(self, spec: RepoSpec) -> dict[str, Any]:
        """注册一个代码仓"""
        if not spec.name:
            raise ValidationError("代码仓 name 为必填")
        if spec.source_type not in ("git", "tar", "api"):
            raise ValidationError(f"不支持的来源类型: {spec.source_type}")
        if spec.source_type == "git" and not spec.url:
            raise ValidationError("git 类型必须指定 url")
        if spec.ref and not _SAFE_REF_RE.match(spec.ref):
            raise ValidationError(f"ref 包含非法字符: {spec.ref}")

        entry: dict[str, Any] = {
            "source_type": spec.source_type,
            "url": spec.url,
            "ref": spec.ref,
            "path": spec.path,
            "tar_path": spec.tar_path,
            "tar_url": spec.tar_url,
            "api_url": spec.api_url,
            "api_token": spec.api_token,
            "setup_cmd": spec.setup_cmd,
            "build_cmd": spec.build_cmd,
            "deps": spec.deps,
        }
        self._put(spec.name, entry)
        logger.info("代码仓已注册: %s (type=%s)", spec.name, spec.source_type)
        return entry

    def get(self, name: str) -> RepoSpec | None:
        """获取已注册代码仓定义"""
        entry = self._get_raw(name)
        if entry is None:
            return None
        return RepoSpec(
            name=name,
            source_type=entry.get("source_type", "git"),
            url=entry.get("url", ""),
            ref=entry.get("ref", "main"),
            path=entry.get("path", ""),
            tar_path=entry.get("tar_path", ""),
            tar_url=entry.get("tar_url", ""),
            api_url=entry.get("api_url", ""),
            api_token=entry.get("api_token", ""),
            setup_cmd=entry.get("setup_cmd", ""),
            build_cmd=entry.get("build_cmd", ""),
            deps=entry.get("deps", []),
        )

    def list_all(self) -> list[dict[str, Any]]:
        return self._list_raw()

    def remove(self, name: str) -> bool:
        if not self._remove(name):
            return False
        logger.info("代码仓已移除: %s", name)
        return True

    # ---- 检出 / 获取 ----

    def checkout(self, name: str, *, ref_override: str = "", shared: bool = True) -> RepoWorkspace:
        """根据来源类型获取代码仓到本地工作目录

        shared=True 时，同 (name, ref) 的已有 checkout 直接复用。
        """
        spec = self.get(name)
        if spec is None:
            raise ValidationError(f"代码仓未注册: {name}")

        ref = ref_override or spec.ref
        cache_key = (name, ref)

        # 复用已有工作目录
        if shared and cache_key in self._workspace_cache:
            cached = self._workspace_cache[cache_key]
            if cached.status not in ("error", "pending"):
                logger.info("复用已有工作目录: %s@%s -> %s", name, ref, cached.local_path)
                return cached

        ws = self._dispatch_checkout(spec, ref)
        self._post_checkout(ws, spec, name)
        self._workspace_cache[cache_key] = ws
        return ws

    def _dispatch_checkout(self, spec: RepoSpec, ref: str) -> RepoWorkspace:
        """按来源类型分派检出"""
        if spec.source_type == "git":
            return self._checkout_git(spec, ref)
        if spec.source_type == "tar":
            return self._checkout_tar(spec, ref)
        if spec.source_type == "api":
            return self._checkout_api(spec, ref)
        raise ValidationError(f"不支持的来源类型: {spec.source_type}")

    def _post_checkout(self, ws: RepoWorkspace, spec: RepoSpec, name: str) -> None:
        """检出后执行依赖解析和 setup/build 步骤"""
        if ws.status in ("error", "pending"):
            return
        if spec.deps:
            self._resolve_deps(spec.deps)
        cwd = Path(ws.local_path)
        if spec.path:
            cwd = cwd / spec.path
        if not cwd.exists():
            ws.status = "error"
            return
        try:
            if spec.setup_cmd:
                run_cmd(spec.setup_cmd, cwd=str(cwd), label="setup")
            if spec.build_cmd:
                run_cmd(spec.build_cmd, cwd=str(cwd), label="build")
            ws.local_path = str(cwd)
        except RuntimeError as e:
            ws.status = "error"
            logger.error("构建步骤失败 %s: %s", name, e)

    def checkout_for_case(self, binding: CaseRepoBinding) -> RepoWorkspace:
        """按用例级绑定检出代码仓（支持分支覆盖 + 复用控制）"""
        return self.checkout(
            binding.repo_name,
            ref_override=binding.ref_override,
            shared=binding.shared,
        )

    # ---- Git 检出 ----

    def _checkout_git(self, spec: RepoSpec, ref: str) -> RepoWorkspace:
        """从Git仓库检出代码到本地工作空间"""
        if ref and not _SAFE_REF_RE.match(ref):
            raise ValidationError(f"ref 包含非法字符: {ref}")

        workspace = self.workspace_root / spec.name / ref.replace("/", "_")
        workspace.mkdir(parents=True, exist_ok=True)
        ws = RepoWorkspace(spec=spec, local_path=str(workspace))

        try:
            self._clone_or_fetch(spec.url, ref, workspace)
            ws.commit_sha = self._get_commit_sha(workspace)
            ws.status = "updated"
            logger.info("Git 就绪: %s@%s -> %s", spec.name, ref, workspace)
        except (subprocess.SubprocessError, OSError) as e:
            ws.status = "error"
            logger.error("Git 检出失败 %s@%s: %s", spec.name, ref, e)

        return ws

    # ---- Tar 解压 ----

    def _checkout_tar(self, spec: RepoSpec, ref: str) -> RepoWorkspace:
        """从tar包解压代码到本地工作空间"""
        workspace = self.workspace_root / spec.name / (ref or "default")
        workspace.mkdir(parents=True, exist_ok=True)
        ws = RepoWorkspace(spec=spec, local_path=str(workspace))

        tar_src = spec.tar_path
        try:
            # 远程 tar 包先下载
            if not tar_src and spec.tar_url:
                from framework.utils.net import validate_url_scheme
                validate_url_scheme(spec.tar_url, context=f"tar download {spec.name}")
                local_tar = workspace.parent / f"{spec.name}.tar.gz"
                urllib.request.urlretrieve(spec.tar_url, str(local_tar))  # nosec B310
                tar_src = str(local_tar)

            if not tar_src:
                raise ValidationError("tar 类型必须指定 tar_path 或 tar_url")

            with tarfile.open(tar_src) as tf:
                tf.extractall(path=str(workspace), filter="data")  # noqa: S202

            ws.status = "extracted"
            logger.info("Tar 解压就绪: %s -> %s", spec.name, workspace)
        except (OSError, tarfile.TarError) as e:
            ws.status = "error"
            logger.error("Tar 解压失败 %s: %s", spec.name, e)

        return ws

    # ---- API 下载 ----

    def _checkout_api(self, spec: RepoSpec, ref: str) -> RepoWorkspace:
        """通过API下载代码包到本地工作空间"""
        workspace = self.workspace_root / spec.name / (ref or "default")
        workspace.mkdir(parents=True, exist_ok=True)
        ws = RepoWorkspace(spec=spec, local_path=str(workspace))

        api_url = spec.api_url
        if not api_url:
            ws.status = "error"
            return ws

        try:
            from framework.utils.net import validate_url_scheme
            validate_url_scheme(api_url, context=f"api download {spec.name}")

            req = urllib.request.Request(api_url)
            if spec.api_token:
                req.add_header("Authorization", f"Bearer {spec.api_token}")

            filename = api_url.rstrip("/").split("/")[-1] or "download"
            dest = workspace / filename
            with urllib.request.urlopen(req, timeout=60) as resp:  # nosec B310
                dest.write_bytes(resp.read())

            # 如果是 tar 包，自动解压
            if dest.suffix in (".gz", ".tgz", ".tar", ".bz2", ".xz"):
                try:
                    with tarfile.open(str(dest)) as tf:
                        tf.extractall(path=str(workspace), filter="data")  # noqa: S202
                except tarfile.TarError:
                    pass  # 非 tar 文件，保持原样

            ws.status = "extracted"
            logger.info("API 下载就绪: %s -> %s", spec.name, workspace)
        except (OSError, urllib.error.URLError) as e:
            ws.status = "error"
            logger.error("API 下载失败 %s: %s", spec.name, e)

        return ws

    # ---- 依赖解析 ----

    @staticmethod
    def _resolve_deps(dep_names: list[str]) -> None:
        """解析代码仓关联的依赖包"""
        try:
            from framework.core.dep_manager import DepManager
            dm = DepManager()
            for dep_name in dep_names:
                try:
                    dm.fetch(dep_name)
                    logger.info("  依赖就绪: %s", dep_name)
                except (OSError, ValueError, RuntimeError) as e:
                    logger.warning("  依赖获取失败（非致命）: %s - %s", dep_name, e)
        except (OSError, ValueError) as e:
            logger.warning("  依赖管理器初始化失败: %s", e)

    # ---- 工作目录管理 ----

    def list_workspaces(self) -> list[dict[str, str]]:
        """列出本地已检出的工作目录"""
        result: list[dict[str, str]] = []
        if not self.workspace_root.exists():
            return result
        for repo_dir in sorted(self.workspace_root.iterdir()):
            if not repo_dir.is_dir():
                continue
            for ref_dir in sorted(repo_dir.iterdir()):
                if not ref_dir.is_dir():
                    continue
                is_git = (ref_dir / ".git").exists()
                sha = self._get_commit_sha(ref_dir) if is_git else ""
                result.append({
                    "repo": repo_dir.name,
                    "ref": ref_dir.name,
                    "path": str(ref_dir),
                    "commit": sha,
                    "type": "git" if is_git else "extracted",
                })
        return result

    def clean(self, name: str) -> int:
        """清理代码仓本地工作目录，返回清理的目录数"""
        repo_dir = self.workspace_root / name
        if not repo_dir.exists():
            return 0
        import shutil
        count = 0
        for child in repo_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
                count += 1
        # 清理缓存
        self._workspace_cache = {
            k: v for k, v in self._workspace_cache.items() if k[0] != name
        }
        logger.info("已清理 %s 的 %d 个工作目录", name, count)
        return count

    # ---- 内部方法 ----

    @staticmethod
    def _clone_or_fetch(url: str, ref: str, workspace: Path) -> None:
        if (workspace / ".git").exists():
            r = subprocess.run(
                ["git", "fetch", "--depth", "1", "origin", ref],
                cwd=str(workspace), capture_output=True, text=True, check=False,
            )
            if r.returncode != 0:
                raise subprocess.SubprocessError(
                    f"git fetch 失败 (rc={r.returncode}): {r.stderr[:300]}"
                )
            r = subprocess.run(
                ["git", "checkout", "FETCH_HEAD"],
                cwd=str(workspace), capture_output=True, text=True, check=False,
            )
            if r.returncode != 0:
                raise subprocess.SubprocessError(
                    f"git checkout 失败 (rc={r.returncode}): {r.stderr[:300]}"
                )
        else:
            result = subprocess.run(
                ["git", "clone", "--depth", "1", "--branch", ref, url, str(workspace)],
                capture_output=True, text=True, check=False,
            )
            if result.returncode != 0:
                # 回退: 完整 clone + checkout
                r2 = subprocess.run(
                    ["git", "clone", url, str(workspace)],
                    capture_output=True, text=True, check=False,
                )
                if r2.returncode != 0:
                    raise subprocess.SubprocessError(
                        f"git clone 失败 (rc={r2.returncode}): {r2.stderr[:300]}"
                    )
                r3 = subprocess.run(
                    ["git", "checkout", ref],
                    cwd=str(workspace), capture_output=True, text=True, check=False,
                )
                if r3.returncode != 0:
                    raise subprocess.SubprocessError(
                        f"git checkout 失败 (rc={r3.returncode}): {r3.stderr[:300]}"
                    )

    @staticmethod
    def _get_commit_sha(workspace: Path) -> str:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True, check=False,
        )
        return r.stdout.strip()[:12] if r.returncode == 0 else ""
