"""代码仓来源适配器 - 支持 Git / Tar / API

职责：
- Git 仓库 clone/fetch
- Tar 包解压（本地/远程）
- API 下载
"""

from __future__ import annotations

import logging
import re
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from framework.core.exceptions import ValidationError
from framework.core.models import RepoSpec, RepoWorkspace

logger = logging.getLogger(__name__)

_SAFE_REF_RE = re.compile(r"^[a-zA-Z0-9_./@\-]+$")


class GitSource:
    """Git 仓库来源"""

    def checkout(self, spec: RepoSpec, ref: str, workspace: Path) -> RepoWorkspace:
        """从Git仓库检出代码到本地工作空间"""
        if ref and not _SAFE_REF_RE.match(ref):
            raise ValidationError(f"ref 包含非法字符: {ref}")

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

    @staticmethod
    def _clone_or_fetch(url: str, ref: str, workspace: Path) -> None:
        """Clone 或 fetch Git 仓库"""
        if (workspace / ".git").exists():
            # 已存在，执行 fetch
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
            # 新 clone
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
        """获取当前 commit SHA"""
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(workspace), capture_output=True, text=True, check=False,
        )
        return r.stdout.strip()[:12] if r.returncode == 0 else ""


class TarSource:
    """Tar 包来源（本地/远程）"""

    def checkout(self, spec: RepoSpec, ref: str, workspace: Path) -> RepoWorkspace:
        """从tar包解压代码到本地工作空间"""
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


class ApiSource:
    """API 下载来源"""

    def checkout(self, spec: RepoSpec, ref: str, workspace: Path) -> RepoWorkspace:
        """通过API下载代码包到本地工作空间"""
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
