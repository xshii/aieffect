"""结果上传器 - 上传结果到远程存储

职责：
- 通过 API 上传结果到云端
- 通过 rsync 上传结果到服务器
- 管理存储配置
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from framework.services.result.query import ResultQuery

from framework.core.result_models import UploadResult

logger = logging.getLogger(__name__)

# 上传类型常量
UPLOAD_LOCAL = "local"
UPLOAD_API = "api"
UPLOAD_RSYNC = "rsync"


class StorageConfig:
    """结果存储服务器配置"""

    def __init__(
        self, *,
        upload_type: str = UPLOAD_LOCAL,
        api_url: str = "",
        api_token: str = "",
        rsync_target: str = "",
        rsync_options: str = "-avz",
        ssh_key: str = "",
        ssh_user: str = "",
    ) -> None:
        self.upload_type = upload_type
        self.api_url = api_url
        self.api_token = api_token
        self.rsync_target = rsync_target
        self.rsync_options = rsync_options
        self.ssh_key = ssh_key
        self.ssh_user = ssh_user

    def to_dict(self) -> dict[str, str]:
        return {
            "upload_type": self.upload_type,
            "api_url": self.api_url,
            "api_token": self.api_token,
            "rsync_target": self.rsync_target,
            "rsync_options": self.rsync_options,
            "ssh_key": self.ssh_key,
            "ssh_user": self.ssh_user,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StorageConfig:
        return cls(
            upload_type=data.get("upload_type", UPLOAD_LOCAL),
            api_url=data.get("api_url", ""),
            api_token=data.get("api_token", ""),
            rsync_target=data.get("rsync_target", ""),
            rsync_options=data.get("rsync_options", "-avz"),
            ssh_key=data.get("ssh_key", ""),
            ssh_user=data.get("ssh_user", ""),
        )


class ResultUploader:
    """结果上传管理器"""

    def __init__(
        self,
        result_dir: str = "",
        query: ResultQuery | None = None,
        storage_config: StorageConfig | None = None,
    ) -> None:
        if not result_dir:
            from framework.core.config import get_config
            result_dir = get_config().result_dir
        self.result_dir = Path(result_dir)
        self._query = query
        self.storage_config = storage_config or StorageConfig()

    def upload(
        self, *,
        config: StorageConfig | None = None,
        run_id: str = "",
    ) -> UploadResult:
        """上传结果到远端存储

        支持三种上传方式:
          - local: 结果已在本地，无需上传
          - api: 通过 HTTP API 上传到云端
          - rsync: 通过 rsync 上传到服务器

        Args:
            config: 存储配置（不传则使用实例默认配置）
            run_id: 关联的 run_id（可选）
        """
        cfg = config or self.storage_config

        if cfg.upload_type == UPLOAD_LOCAL:
            return UploadResult(
                status="success",
                type="local",
                path=str(self.result_dir),
                message="结果已保存在本地",
            )
        if cfg.upload_type == UPLOAD_API:
            return self._upload_via_api(cfg, run_id)
        if cfg.upload_type == UPLOAD_RSYNC:
            return self._upload_via_rsync(cfg)

        return UploadResult(
            status="error",
            type=cfg.upload_type,
            message=f"不支持的上传类型: {cfg.upload_type}",
        )

    def _upload_via_api(
        self, cfg: StorageConfig, run_id: str,
    ) -> UploadResult:
        """通过 API 上传结果到云端"""
        if not cfg.api_url:
            return UploadResult(
                status="error",
                type="api",
                message="API 上传需要配置 api_url",
            )

        from framework.utils.net import validate_url_scheme
        validate_url_scheme(cfg.api_url, context="result upload")

        import urllib.error
        import urllib.request

        # 获取结果并序列化
        if self._query is None:
            return UploadResult(
                status="error",
                type="api",
                message="无法获取结果：未提供 query",
            )

        results_obj = self._query.list_results()
        data = results_obj.to_dict()
        data["run_id"] = run_id
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            cfg.api_url, data=body, method="POST",
            headers={"Content-Type": "application/json"},
        )
        if cfg.api_token:
            req.add_header("Authorization", f"Bearer {cfg.api_token}")

        try:
            with urllib.request.urlopen(req) as resp:  # nosec B310
                resp_data = json.loads(resp.read().decode("utf-8"))
            return UploadResult(
                status="success",
                type="api",
                response=resp_data,
            )
        except urllib.error.HTTPError as e:
            return UploadResult(
                status="error",
                type="api",
                message=f"HTTP 错误 {e.code}: {e.reason}",
            )
        except urllib.error.URLError as e:
            return UploadResult(
                status="error",
                type="api",
                message=f"网络错误: {e.reason}",
            )
        except json.JSONDecodeError as e:
            return UploadResult(
                status="error",
                type="api",
                message=f"响应格式错误: {e}",
            )
        except (OSError, ValueError) as e:
            return UploadResult(
                status="error",
                type="api",
                message=str(e),
            )

    def _upload_via_rsync(self, cfg: StorageConfig) -> UploadResult:
        """通过 rsync 上传结果到服务器"""
        if not cfg.rsync_target:
            return UploadResult(
                status="error",
                type="rsync",
                message="rsync 上传需要配置 rsync_target",
            )

        cmd_parts = self._build_rsync_cmd(cfg)
        logger.info("rsync 上传: %s", " ".join(cmd_parts))

        try:
            r = subprocess.run(
                cmd_parts, capture_output=True, text=True,
                check=False, timeout=600,
            )
        except subprocess.TimeoutExpired:
            return UploadResult(
                status="error",
                type="rsync",
                message="rsync 超时 (600s)",
            )
        except FileNotFoundError:
            return UploadResult(
                status="error",
                type="rsync",
                message="rsync 未安装，请先安装: apt install rsync / yum install rsync",
            )

        return self._parse_rsync_result(r, cfg.rsync_target)

    def _build_rsync_cmd(self, cfg: StorageConfig) -> list[str]:
        """构造 rsync 命令"""
        cmd_parts = ["rsync"] + shlex.split(cfg.rsync_options)
        if cfg.ssh_key:
            cmd_parts.extend(["-e", f"ssh -i {cfg.ssh_key}"])
        elif cfg.ssh_user:
            cmd_parts.extend(["-e", f"ssh -l {cfg.ssh_user}"])
        cmd_parts.append(str(self.result_dir) + "/")
        cmd_parts.append(cfg.rsync_target)
        return cmd_parts

    @staticmethod
    def _parse_rsync_result(r: subprocess.CompletedProcess[str], target: str) -> UploadResult:
        """解析 rsync 结果"""
        if r.returncode == 0:
            return UploadResult(
                status="success",
                type="rsync",
                target=target,
            )

        # 权限错误
        if r.returncode in (12, 23) or "Permission denied" in r.stderr:
            return UploadResult(
                status="error",
                type="rsync",
                message=f"权限不足 (rc={r.returncode}): {r.stderr[:300]}",
                hint=(
                    "请检查权限配置:\n"
                    "  1. 确认 SSH 密钥已添加: ssh_key 参数或 ssh-add\n"
                    "  2. 确认目标目录写权限: ssh user@host 'ls -la /target'\n"
                    "  3. 确认 rsync 已安装: which rsync\n"
                    "  4. 配置免密登录: ssh-copy-id user@host"
                ),
            )

        # 其他错误
        return UploadResult(
            status="error",
            type="rsync",
            message=f"rsync 失败 (rc={r.returncode}): {r.stderr[:500]}",
        )
