"""结果服务 — 统一结果存储 / 查询 / 对比 / 导出 / 上传

将 collector + history + reporter 整合为统一的结果管理 API，
提供结果生命周期管理。

支持:
  - 测试元信息存储（代码仓、环境等上下文）
  - 测试结果数据的获取路径配置
  - 结果上传: 云端 API / rsync 服务器 / 本地保存
  - 存储服务器配置
"""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from framework.core.history import HistoryManager
from framework.core.models import SuiteResult, summarize_statuses
from framework.core.result_models import (
    CompareError,
    CompareResponse,
    CompareResult,
    ListResultsResponse,
    RunInfo,
    UploadResult,
    dict_to_summary,
)

logger = logging.getLogger(__name__)


# =========================================================================
# 存储目标配置
# =========================================================================

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


class ResultService:
    """统一结果管理"""

    def __init__(
        self, result_dir: str = "", history_file: str = "",
        storage_config: StorageConfig | None = None,
    ) -> None:
        if not result_dir:
            from framework.core.config import get_config
            result_dir = get_config().result_dir
        self.result_dir = Path(result_dir)
        self.result_dir.mkdir(parents=True, exist_ok=True)
        self.history = HistoryManager(history_file=history_file)
        self.storage_config = storage_config or StorageConfig()

    # ---- 保存 ----

    def save(self, suite_result: SuiteResult, **context: Any) -> str:
        """保存一次执行结果（持久化 + 历史记录），返回 run_id

        结果包含测试元信息和结果数据路径配置。
        """
        self._persist_results(suite_result)
        meta = self._collect_context_dict(
            context,
            ("repo_name", "repo_ref", "repo_commit",
             "build_env", "exe_env", "stimulus_name"),
            extra_key="extra_meta",
        )
        result_paths = self._collect_context_dict(
            context,
            ("log_path", "waveform_path", "coverage_path",
             "report_path", "artifact_dir"),
            extra_key="custom_paths",
        )
        entry = self.history.record_run(
            suite=context.get("suite", suite_result.suite_name),
            results=[asdict(r) for r in suite_result.results],
            environment=context.get("environment", suite_result.environment),
            snapshot_id=context.get(
                "snapshot_id", suite_result.snapshot_id,
            ),
            params=context.get("params"),
            meta=meta or None,
            result_paths=result_paths or None,
        )
        logger.info(
            "结果已保存: run_id=%s, %d 条",
            entry["run_id"], len(suite_result.results),
        )
        return str(entry["run_id"])

    def _persist_results(self, suite_result: SuiteResult) -> None:
        for r in suite_result.results:
            f = self.result_dir / f"{r.name}.json"
            f.write_text(
                json.dumps(asdict(r), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    @staticmethod
    def _collect_context_dict(
        context: dict[str, Any], keys: tuple[str, ...],
        *, extra_key: str = "",
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key in keys:
            val = context.get(key, "")
            if val:
                result[key] = val
        if extra_key and context.get(extra_key):
            result.update(context[extra_key])
        return result

    # ---- 查询 ----

    def get_result(self, case_name: str) -> dict[str, Any] | None:
        """获取单个用例的最新结果"""
        f = self.result_dir / f"{case_name}.json"
        if not f.exists():
            return None
        result: dict[str, Any] = json.loads(f.read_text(encoding="utf-8"))
        return result

    def list_results(self) -> ListResultsResponse:
        """列出所有结果及汇总"""
        results: list[dict[str, Any]] = []
        if self.result_dir.exists():
            for f in sorted(self.result_dir.glob("*.json")):
                if f.name.startswith("report"):
                    continue
                try:
                    results.append(
                        json.loads(f.read_text(encoding="utf-8")),
                    )
                except json.JSONDecodeError:
                    pass
        summary_dict = summarize_statuses(results)
        return ListResultsResponse(
            summary=dict_to_summary(summary_dict),
            results=results,
        )

    def query_history(
        self, *, suite: str | None = None, environment: str | None = None,
        case_name: str | None = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """查询执行历史"""
        return self.history.query(
            suite=suite, environment=environment,
            case_name=case_name, limit=limit,
        )

    def case_summary(self, case_name: str) -> dict[str, Any]:
        """获取单个用例的历史执行汇总"""
        return self.history.case_summary(case_name)

    # ---- 对比 ----

    def compare_runs(self, run_id_a: str, run_id_b: str) -> CompareResponse:
        """对比两次执行结果"""
        # 输入验证
        if not run_id_a or not run_id_b:
            return CompareError(error="run_id 不能为空")
        if run_id_a == run_id_b:
            return CompareError(error="不能对比相同的 run_id")

        # 查找记录
        rec_a, rec_b = self._find_records(run_id_a, run_id_b)
        if rec_a is None or rec_b is None:
            missing = [
                rid for rid, rec in ((run_id_a, rec_a), (run_id_b, rec_b))
                if rec is None
            ]
            return CompareError(error=f"未找到记录: {', '.join(missing)}")

        # 计算差异
        diffs, total = self._compute_diffs(rec_a, rec_b, run_id_a, run_id_b)
        return CompareResult(
            run_a=RunInfo(run_id=run_id_a, summary=rec_a.get("summary", {})),
            run_b=RunInfo(run_id=run_id_b, summary=rec_b.get("summary", {})),
            diffs=diffs,
            total_cases=total,
            changed_cases=len(diffs),
        )

    def _find_records(
        self, run_id_a: str, run_id_b: str,
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        all_records = self.history.query(limit=10000)
        rec_a: dict[str, Any] | None = None
        rec_b: dict[str, Any] | None = None
        for r in all_records:
            rid = r.get("run_id")
            if rid == run_id_a:
                rec_a = r
            elif rid == run_id_b:
                rec_b = r
            if rec_a is not None and rec_b is not None:
                break
        return rec_a, rec_b

    @staticmethod
    def _compute_diffs(
        rec_a: dict[str, Any], rec_b: dict[str, Any],
        run_id_a: str, run_id_b: str,
    ) -> tuple[list[dict[str, str]], int]:
        cases_a = {r["name"]: r for r in rec_a.get("results", [])}
        cases_b = {r["name"]: r for r in rec_b.get("results", [])}
        all_names = sorted(set(cases_a) | set(cases_b))
        diffs: list[dict[str, str]] = []
        for name in all_names:
            a_status = cases_a.get(name, {}).get("status", "—")
            b_status = cases_b.get(name, {}).get("status", "—")
            if a_status != b_status:
                diffs.append(
                    {"case": name, run_id_a: a_status, run_id_b: b_status},
                )
        return diffs, len(all_names)

    # ---- 导出 ----

    def export(self, fmt: str = "html") -> str:
        """生成报告，返回报告文件路径"""
        from framework.core.reporter import generate_report
        return generate_report(result_dir=str(self.result_dir), fmt=fmt)

    # ---- 上传 ----

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
        results_obj = self.list_results()
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

    # ---- 清理 ----

    def clean_results(self) -> int:
        """清理结果目录下的所有 JSON 文件"""
        count = 0
        for f in self.result_dir.glob("*.json"):
            f.unlink()
            count += 1
        logger.info("已清理 %d 个结果文件", count)
        return count
