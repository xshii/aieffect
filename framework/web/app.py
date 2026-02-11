"""轻量级 Web 看板（基于 Flask）

提供：回归结果查看、依赖包状态、手动触发回归、上传依赖包、
      用例表单管理、执行历史、日志检查、资源状态、外部结果录入、
      存储对接、环境管理、激励管理、构建管理、结果管理、编排执行。

启动方式: aieffect dashboard --port 8888
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH


# =========================================================================
# 全局 JSON 错误处理
# =========================================================================


def _safe_int(value: Any, default: int, lo: int = 1, hi: int = 10000) -> int:
    """安全的整数转换，带范围校验"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(n, hi))


_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_safe_name(value: str, field: str) -> str:
    """校验参数仅包含安全字符（字母/数字/下划线/连字符），防止注入"""
    value = str(value).strip()
    if not _SAFE_NAME_RE.match(value):
        raise ValueError(f"参数 '{field}' 包含非法字符: {value}")
    return value


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    """将所有 HTTP 异常统一返回 JSON"""
    return jsonify(error=exc.description), exc.code


@app.errorhandler(Exception)
def handle_generic_exception(exc):  # noqa: ARG001
    """捕获未处理异常，返回 500 JSON"""
    logger.exception("未处理的异常")
    return jsonify(error="服务器内部错误"), 500


@app.route("/")
def index():
    return render_template("dashboard.html")


# =========================================================================
# 原有 API
# =========================================================================


@app.route("/api/results")
def api_results():
    """查询回归结果列表"""
    from framework.core.config import get_config
    result_dir = Path(get_config().result_dir)
    results = []
    if result_dir.exists():
        for f in sorted(result_dir.glob("*.json")):
            if f.name.startswith("report"):
                continue
            try:
                results.append(json.loads(f.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass

    from framework.core.models import summarize_statuses
    return jsonify(summary=summarize_statuses(results), results=results)


@app.route("/api/deps")
def api_deps():
    """查询依赖包列表"""
    from framework.core.config import get_config
    manifest = Path(get_config().manifest)
    if not manifest.exists():
        return jsonify(packages=[])

    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    packages = []
    for name, info in (data.get("packages") or {}).items():
        if info:
            packages.append({"name": name, **info})
    return jsonify(packages=packages)


def _wait_and_log(proc: subprocess.Popen[str], cmd: list[str]) -> None:
    """后台线程等待子进程结束，避免僵尸进程"""
    try:
        stdout, _ = proc.communicate()
        logger.info("回归完成 (pid=%d, rc=%d): %s", proc.pid, proc.returncode, cmd)
        if proc.returncode != 0 and stdout:
            logger.warning("回归输出 (pid=%d):\n%s", proc.pid, stdout[:2000])
    except (OSError, subprocess.SubprocessError):
        logger.exception("等待回归进程 (pid=%d) 时出错", proc.pid)


def _build_run_cmd(body: dict[str, Any]) -> list[str]:
    """从请求体构建 aieffect run 命令，参数不合法时抛 ValueError"""
    suite = _validate_safe_name(body.get("suite", "default"), "suite")
    parallel = _safe_int(body.get("parallel", 1), default=1, lo=1, hi=64)

    configs_base = Path("configs").resolve()
    config_file = (configs_base / body.get("config", "default.yml")).resolve()
    if not str(config_file).startswith(str(configs_base)):
        raise ValueError("config 路径不合法")
    if not config_file.suffix:
        config_file = config_file.with_suffix(".yml")

    cmd = ["aieffect", "run", suite, "-p", str(parallel), "-c", str(config_file)]

    for flag, key in [("-e", "environment"), ("--snapshot", "snapshot")]:
        val = body.get(key, "")
        if val:
            cmd.extend([flag, _validate_safe_name(val, key)])

    for k, v in (body.get("params") or {}).items():
        cmd.extend(["--param", f"{k}={v}"])

    for cn in body.get("cases") or []:
        cmd.extend(["--case", _validate_safe_name(cn, "case")])

    return cmd


@app.route("/api/run", methods=["POST"])
def api_run():
    body = request.get_json(silent=True) or {}
    try:
        cmd = _build_run_cmd(body)
    except (ValueError, TypeError) as e:
        return jsonify(error=str(e)), 400

    logger.info("手动触发回归: %s", cmd)
    proc = subprocess.Popen(  # noqa: SIM115 — daemon thread 管理生命周期
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    threading.Thread(target=_wait_and_log, args=(proc, cmd), daemon=True).start()
    return jsonify(message="回归已触发", pid=proc.pid, command=" ".join(cmd))


@app.route("/api/deps/upload", methods=["POST"])
def api_upload_dep():
    name = request.form.get("name", "")
    version = request.form.get("version", "")
    file = request.files.get("file")

    if not name or not version or not file or not file.filename:
        return jsonify(error="需要提供 name、version 和 file"), 400

    try:
        name = _validate_safe_name(name, "name")
        version = _validate_safe_name(version, "version")
    except ValueError as e:
        return jsonify(error=str(e)), 400

    safe_name = secure_filename(file.filename)
    if not safe_name:
        return jsonify(error="文件名不合法"), 400

    base_dir = Path("deps/packages").resolve()
    upload_dir = (base_dir / name / version).resolve()

    if not str(upload_dir).startswith(str(base_dir)):
        return jsonify(error="路径不合法"), 400

    upload_dir.mkdir(parents=True, exist_ok=True)
    dest = upload_dir / safe_name
    file.save(str(dest))

    logger.info("依赖包已上传: %s@%s -> %s", name, version, dest)
    return jsonify(message=f"已上传 {name}@{version}", path=str(dest))


# =========================================================================
# 用例表单管理 API
# =========================================================================


@app.route("/api/cases", methods=["GET"])
def api_cases_list():
    from framework.core.case_manager import CaseManager
    cm = CaseManager()
    tag = request.args.get("tag")
    env = request.args.get("environment")
    return jsonify(cases=cm.list_cases(tag=tag, environment=env))


@app.route("/api/cases/<name>", methods=["GET"])
def api_cases_get(name: str):
    from framework.core.case_manager import CaseManager
    cm = CaseManager()
    case = cm.get_case(name)
    if case is None:
        return jsonify(error="用例不存在"), 404
    return jsonify(case=case)


@app.route("/api/cases", methods=["POST"])
def api_cases_add():
    from framework.core.case_manager import CaseManager
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    cmd = body.get("cmd", "")
    if not name or not cmd:
        return jsonify(error="需要提供 name 和 cmd"), 400

    cm = CaseManager()
    case = cm.add_case(
        name, cmd,
        description=body.get("description", ""),
        tags=body.get("tags", []),
        timeout=body.get("timeout", 3600),
        environments=body.get("environments", []),
        params_schema=body.get("params_schema"),
    )
    return jsonify(message=f"用例已保存: {name}", case={"name": name, **case})


@app.route("/api/cases/<name>", methods=["PUT"])
def api_cases_update(name: str):
    from framework.core.case_manager import CaseManager
    body = request.get_json(silent=True) or {}  # type: ignore[attr-defined]
    cm = CaseManager()
    updated = cm.update_case(name, **body)
    if updated is None:
        return jsonify(error="用例不存在"), 404
    return jsonify(message=f"用例已更新: {name}", case=updated)


@app.route("/api/cases/<name>", methods=["DELETE"])
def api_cases_delete(name: str):
    from framework.core.case_manager import CaseManager
    cm = CaseManager()
    if cm.remove_case(name):
        return jsonify(message=f"用例已删除: {name}")
    return jsonify(error="用例不存在"), 404


# =========================================================================
# 环境管理 API（旧 — CaseManager 环境）
# =========================================================================


@app.route("/api/environments", methods=["GET"])
def api_env_list():
    from framework.core.case_manager import CaseManager
    cm = CaseManager()
    return jsonify(environments=cm.list_environments())


@app.route("/api/environments", methods=["POST"])
def api_env_add():
    from framework.core.case_manager import CaseManager
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400

    cm = CaseManager()
    env = cm.add_environment(
        name, description=body.get("description", ""),
        variables=body.get("variables"),
    )
    return jsonify(message=f"环境已保存: {name}", environment={"name": name, **env})


# =========================================================================
# 构建版本快照 API
# =========================================================================


@app.route("/api/snapshots", methods=["GET"])
def api_snapshots_list():
    from framework.core.snapshot import SnapshotManager
    sm = SnapshotManager()
    return jsonify(snapshots=sm.list_snapshots())


@app.route("/api/snapshots", methods=["POST"])
def api_snapshots_create():
    from framework.core.snapshot import SnapshotManager
    body = request.get_json(silent=True) or {}
    sm = SnapshotManager()
    snap = sm.create(description=body.get("description", ""), snapshot_id=body.get("id"))
    return jsonify(message=f"快照已创建: {snap['id']}", snapshot=snap)


@app.route("/api/snapshots/<snapshot_id>", methods=["GET"])
def api_snapshots_get(snapshot_id: str):
    from framework.core.snapshot import SnapshotManager
    sm = SnapshotManager()
    snap = sm.get(snapshot_id)
    if snap is None:
        return jsonify(error="快照不存在"), 404
    return jsonify(snapshot=snap)


@app.route("/api/snapshots/<snapshot_id>/restore", methods=["POST"])
def api_snapshots_restore(snapshot_id: str):
    from framework.core.snapshot import SnapshotManager
    sm = SnapshotManager()
    if sm.restore(snapshot_id):
        return jsonify(message=f"快照已恢复: {snapshot_id}")
    return jsonify(error="快照不存在"), 404


# =========================================================================
# 执行历史 API
# =========================================================================


@app.route("/api/history", methods=["GET"])
def api_history_list():
    from framework.core.history import HistoryManager
    hm = HistoryManager()
    records = hm.query(
        suite=request.args.get("suite"),
        environment=request.args.get("environment"),
        case_name=request.args.get("case_name"),
        limit=_safe_int(request.args.get("limit", 50), default=50),
    )
    return jsonify(records=records)


@app.route("/api/history/case/<case_name>", methods=["GET"])
def api_history_case(case_name: str):
    from framework.core.history import HistoryManager
    hm = HistoryManager()
    return jsonify(summary=hm.case_summary(case_name))


@app.route("/api/history/submit", methods=["POST"])
def api_history_submit():
    """接收本地执行后通过 API 录入的执行结果"""
    from framework.core.history import HistoryManager
    body = request.get_json(silent=True) or {}

    if "suite" not in body or "results" not in body:
        return jsonify(error="需要提供 suite 和 results"), 400

    hm = HistoryManager()
    try:
        entry = hm.submit_external(body)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(message="执行结果已录入", entry=entry)


# =========================================================================
# 日志检查 API
# =========================================================================


@app.route("/api/check-log", methods=["POST"])
def api_check_log():
    """上传日志文件并执行规则匹配检查"""
    from framework.core.log_checker import LogChecker

    rules_file = request.args.get("rules", "configs/log_rules.yml")
    checker = LogChecker(rules_file=rules_file)

    file = request.files.get("file")
    text = None
    source = ""

    if file and file.filename:
        text = file.read().decode(errors="replace")
        source = secure_filename(file.filename)
    else:
        body = request.get_json(silent=True) or {}
        text = body.get("text", "")
        source = body.get("source", "api_input")

    if not text:
        return jsonify(error="需要提供日志文件或 text 字段"), 400

    report = checker.check_text(text, source=source)
    return jsonify(
        success=report.success,
        log_source=report.log_source,
        total_rules=report.total_rules,
        passed_rules=report.passed_rules,
        failed_rules=report.failed_rules,
        details=[asdict(d) for d in report.details],
    )


# =========================================================================
# 资源状态 API
# =========================================================================


@app.route("/api/resource", methods=["GET"])
def api_resource_status():
    from framework.core.resource import ResourceManager
    rm = ResourceManager()
    s = rm.status()
    return jsonify(asdict(s))


# =========================================================================
# 存储层 API
# =========================================================================


@app.route("/api/storage/<namespace>", methods=["GET"])
def api_storage_list(namespace: str):
    try:
        namespace = _validate_safe_name(namespace, "namespace")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    from framework.core.storage import create_storage
    storage = create_storage()
    keys = storage.list_keys(namespace)
    return jsonify(namespace=namespace, keys=keys)


@app.route("/api/storage/<namespace>/<key>", methods=["GET"])
def api_storage_get(namespace: str, key: str):
    try:
        namespace = _validate_safe_name(namespace, "namespace")
        key = _validate_safe_name(key, "key")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    from framework.core.storage import create_storage
    storage = create_storage()
    data = storage.get(namespace, key)
    if data is None:
        return jsonify(error="数据不存在"), 404
    return jsonify(data=data)


@app.route("/api/storage/<namespace>/<key>", methods=["PUT"])
def api_storage_put(namespace: str, key: str):
    try:
        namespace = _validate_safe_name(namespace, "namespace")
        key = _validate_safe_name(key, "key")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    from framework.core.storage import create_storage
    body = request.get_json(silent=True) or {}  # type: ignore[attr-defined]
    storage = create_storage()
    path = storage.put(namespace, key, body)
    return jsonify(message="已存储", path=path)


# =========================================================================
# 代码仓 API
# =========================================================================


@app.route("/api/repos", methods=["GET"])
def api_repos_list():
    from framework.services.repo_service import RepoService
    svc = RepoService()
    return jsonify(repos=svc.list_all())


@app.route("/api/repos/<name>", methods=["GET"])
def api_repos_get(name: str):
    from framework.services.repo_service import RepoService
    svc = RepoService()
    spec = svc.get(name)
    if spec is None:
        return jsonify(error="代码仓不存在"), 404
    return jsonify(repo=asdict(spec))


@app.route("/api/repos", methods=["POST"])
def api_repos_add():
    from framework.core.models import RepoSpec
    from framework.services.repo_service import RepoService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    svc = RepoService()
    spec = RepoSpec(
        name=name,
        source_type=body.get("source_type", "git"),
        url=body.get("url", ""),
        ref=body.get("ref", "main"),
        path=body.get("path", ""),
        tar_path=body.get("tar_path", ""),
        tar_url=body.get("tar_url", ""),
        api_url=body.get("api_url", ""),
        api_token=body.get("api_token", ""),
        setup_cmd=body.get("setup_cmd", ""),
        build_cmd=body.get("build_cmd", ""),
        deps=body.get("deps", []),
    )
    entry = svc.register(spec)
    return jsonify(message=f"代码仓已注册: {name}", repo=entry)


@app.route("/api/repos/<name>", methods=["DELETE"])
def api_repos_delete(name: str):
    from framework.services.repo_service import RepoService
    svc = RepoService()
    if svc.remove(name):
        return jsonify(message=f"代码仓已删除: {name}")
    return jsonify(error="代码仓不存在"), 404


@app.route("/api/repos/<name>/checkout", methods=["POST"])
def api_repos_checkout(name: str):
    from framework.services.repo_service import RepoService
    body = request.get_json(silent=True) or {}  # type: ignore[attr-defined]
    svc = RepoService()
    ws = svc.checkout(name, ref_override=body.get("ref", ""))
    return jsonify(
        repo=name, status=ws.status,
        local_path=ws.local_path, commit=ws.commit_sha,
    )


@app.route("/api/repos/workspaces", methods=["GET"])
def api_repos_workspaces():
    from framework.services.repo_service import RepoService
    svc = RepoService()
    return jsonify(workspaces=svc.list_workspaces())


# =========================================================================
# 环境服务 API（BuildEnv + ExeEnv）
# =========================================================================


@app.route("/api/envs", methods=["GET"])
def api_envs_list():
    from framework.services.env_service import EnvService
    svc = EnvService()
    return jsonify(environments=svc.list_all())


@app.route("/api/envs/build", methods=["GET"])
def api_envs_build_list():
    from framework.services.env_service import EnvService
    svc = EnvService()
    return jsonify(build_envs=svc.list_build_envs())


@app.route("/api/envs/exe", methods=["GET"])
def api_envs_exe_list():
    from framework.services.env_service import EnvService
    svc = EnvService()
    return jsonify(exe_envs=svc.list_exe_envs())


@app.route("/api/envs/build", methods=["POST"])
def api_envs_build_add():
    from framework.core.models import BuildEnvSpec
    from framework.services.env_service import EnvService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    spec = BuildEnvSpec(
        name=name,
        build_env_type=body.get("build_env_type", "local"),
        description=body.get("description", ""),
        work_dir=body.get("work_dir", ""),
        variables=body.get("variables", {}),
        host=body.get("host", ""),
        port=body.get("port", 22),
        user=body.get("user", ""),
        key_path=body.get("key_path", ""),
    )
    svc = EnvService()
    entry = svc.register_build_env(spec)
    return jsonify(message=f"构建环境已注册: {name}", build_env=entry)


@app.route("/api/envs/exe", methods=["POST"])
def api_envs_exe_add():
    from framework.core.models import ExeEnvSpec, ToolSpec
    from framework.services.env_service import EnvService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    tools: dict[str, ToolSpec] = {}
    for tname, tinfo in (body.get("tools") or {}).items():
        ti = tinfo if isinstance(tinfo, dict) else {}
        tools[tname] = ToolSpec(
            name=tname, version=ti.get("version", ""),
            install_path=ti.get("install_path", ""),
            env_vars=ti.get("env_vars", {}),
        )
    spec = ExeEnvSpec(
        name=name,
        exe_env_type=body.get("exe_env_type", "eda"),
        description=body.get("description", ""),
        api_url=body.get("api_url", ""),
        api_token=body.get("api_token", ""),
        variables=body.get("variables", {}),
        tools=tools,
        licenses=body.get("licenses", {}),
        timeout=body.get("timeout", 3600),
        build_env_name=body.get("build_env_name", ""),
    )
    svc = EnvService()
    entry = svc.register_exe_env(spec)
    return jsonify(message=f"执行环境已注册: {name}", exe_env=entry)


@app.route("/api/envs/build/<name>", methods=["DELETE"])
def api_envs_build_delete(name: str):
    from framework.services.env_service import EnvService
    svc = EnvService()
    if svc.remove_build_env(name):
        return jsonify(message=f"构建环境已删除: {name}")
    return jsonify(error="构建环境不存在"), 404


@app.route("/api/envs/exe/<name>", methods=["DELETE"])
def api_envs_exe_delete(name: str):
    from framework.services.env_service import EnvService
    svc = EnvService()
    if svc.remove_exe_env(name):
        return jsonify(message=f"执行环境已删除: {name}")
    return jsonify(error="执行环境不存在"), 404


@app.route("/api/envs/apply", methods=["POST"])
def api_envs_apply():
    from framework.services.env_service import EnvService
    body = request.get_json(silent=True) or {}
    svc = EnvService()
    try:
        session = svc.apply(
            build_env_name=body.get("build_env_name", ""),
            exe_env_name=body.get("exe_env_name", ""),
        )
        return jsonify(
            session_id=session.session_id,
            name=session.name,
            status=session.status,
            work_dir=session.work_dir,
            variables_count=len(session.resolved_vars),
        )
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route("/api/envs/sessions", methods=["GET"])
def api_envs_sessions():
    from framework.services.env_service import EnvService
    svc = EnvService()
    return jsonify(sessions=svc.list_sessions())


@app.route("/api/envs/sessions/<session_id>/release", methods=["POST"])
def api_envs_release(session_id: str):
    from framework.services.env_service import EnvService
    svc = EnvService()
    session = svc.get_session(session_id)
    if session is None:
        return jsonify(error="会话不存在"), 404
    svc.release(session)
    return jsonify(message="环境已释放", session_id=session_id)


@app.route("/api/envs/sessions/<session_id>/timeout", methods=["POST"])
def api_envs_timeout(session_id: str):
    from framework.services.env_service import EnvService
    svc = EnvService()
    session = svc.get_session(session_id)
    if session is None:
        return jsonify(error="会话不存在"), 404
    svc.timeout(session)
    return jsonify(message="环境已超时", session_id=session_id)


@app.route("/api/envs/sessions/<session_id>/invalid", methods=["POST"])
def api_envs_invalid(session_id: str):
    from framework.services.env_service import EnvService
    svc = EnvService()
    session = svc.get_session(session_id)
    if session is None:
        return jsonify(error="会话不存在"), 404
    svc.invalid(session)
    return jsonify(message="环境已失效", session_id=session_id)


@app.route("/api/envs/execute", methods=["POST"])
def api_envs_execute():
    from framework.services.env_service import EnvService
    body = request.get_json(silent=True) or {}  # type: ignore[attr-defined]
    cmd = body.get("cmd", "")
    if not cmd:
        return jsonify(error="需要提供 cmd"), 400
    svc = EnvService()
    try:
        session = svc.apply(
            build_env_name=body.get("build_env_name", ""),
            exe_env_name=body.get("exe_env_name", ""),
        )
        result = svc.execute_in(
            session, cmd, timeout=body.get("timeout", 3600),
        )
        svc.release(session)
        return jsonify(result=result)
    except Exception as e:
        return jsonify(error=str(e)), 400


# =========================================================================
# 激励管理 API
# =========================================================================


@app.route("/api/stimuli", methods=["GET"])
def api_stimuli_list():
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    return jsonify(stimuli=svc.list_all())


@app.route("/api/stimuli/<name>", methods=["GET"])
def api_stimuli_get(name: str):
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    spec = svc.get(name)
    if spec is None:
        return jsonify(error="激励不存在"), 404
    result = asdict(spec)
    return jsonify(stimulus=result)


@app.route("/api/stimuli", methods=["POST"])
def api_stimuli_add():
    from framework.core.models import RepoSpec, StimulusSpec
    from framework.services.stimulus_service import StimulusService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400

    repo = None
    if body.get("repo"):
        r = body["repo"]
        repo = RepoSpec(
            name=r.get("name", name), url=r.get("url", ""),
            ref=r.get("ref", "main"),
        )

    spec = StimulusSpec(
        name=name, source_type=body.get("source_type", "repo"),
        repo=repo, generator_cmd=body.get("generator_cmd", ""),
        storage_key=body.get("storage_key", ""),
        external_url=body.get("external_url", ""),
        description=body.get("description", ""),
        params=body.get("params", {}),
        template=body.get("template", ""),
    )
    svc = StimulusService()
    entry = svc.register(spec)
    return jsonify(message=f"激励已注册: {name}", stimulus=entry)


@app.route("/api/stimuli/<name>", methods=["DELETE"])
def api_stimuli_delete(name: str):
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    if svc.remove(name):
        return jsonify(message=f"激励已删除: {name}")
    return jsonify(error="激励不存在"), 404


@app.route("/api/stimuli/<name>/acquire", methods=["POST"])
def api_stimuli_acquire(name: str):
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    try:
        art = svc.acquire(name)
        return jsonify(
            name=name, status=art.status,
            local_path=art.local_path, checksum=art.checksum,
        )
    except Exception as e:
        return jsonify(error=str(e)), 400


@app.route("/api/stimuli/<name>/construct", methods=["POST"])
def api_stimuli_construct(name: str):
    from framework.services.stimulus_service import StimulusService
    body = request.get_json(silent=True) or {}  # type: ignore[attr-defined]
    svc = StimulusService()
    try:
        art = svc.construct(name, params=body.get("params"))
        return jsonify(
            name=name, status=art.status,
            local_path=art.local_path, checksum=art.checksum,
        )
    except Exception as e:
        return jsonify(error=str(e)), 400


# ---- 结果激励 API ----

@app.route("/api/stimuli/result", methods=["GET"])
def api_result_stimuli_list():
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    return jsonify(result_stimuli=svc.list_result_stimuli())


@app.route("/api/stimuli/result", methods=["POST"])
def api_result_stimuli_add():
    from framework.core.models import ResultStimulusSpec
    from framework.services.stimulus_service import StimulusService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    spec = ResultStimulusSpec(
        name=name,
        source_type=body.get("source_type", "api"),
        api_url=body.get("api_url", ""),
        api_token=body.get("api_token", ""),
        binary_path=body.get("binary_path", ""),
        parser_cmd=body.get("parser_cmd", ""),
        description=body.get("description", ""),
    )
    svc = StimulusService()
    entry = svc.register_result_stimulus(spec)
    return jsonify(message=f"结果激励已注册: {name}", result_stimulus=entry)


@app.route("/api/stimuli/result/<name>/collect", methods=["POST"])
def api_result_stimuli_collect(name: str):
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    try:
        art = svc.collect_result_stimulus(name)
        return jsonify(
            name=name, status=art.status,
            local_path=art.local_path, data=art.data,
        )
    except Exception as e:
        return jsonify(error=str(e)), 400


# ---- 激励触发 API ----

@app.route("/api/stimuli/triggers", methods=["GET"])
def api_triggers_list():
    from framework.services.stimulus_service import StimulusService
    svc = StimulusService()
    return jsonify(triggers=svc.list_triggers())


@app.route("/api/stimuli/triggers", methods=["POST"])
def api_triggers_add():
    from framework.core.models import TriggerSpec
    from framework.services.stimulus_service import StimulusService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    spec = TriggerSpec(
        name=name,
        trigger_type=body.get("trigger_type", "api"),
        api_url=body.get("api_url", ""),
        api_token=body.get("api_token", ""),
        binary_cmd=body.get("binary_cmd", ""),
        stimulus_name=body.get("stimulus_name", ""),
        description=body.get("description", ""),
    )
    svc = StimulusService()
    entry = svc.register_trigger(spec)
    return jsonify(message=f"触发器已注册: {name}", trigger=entry)


@app.route("/api/stimuli/triggers/<name>/fire", methods=["POST"])
def api_triggers_fire(name: str):
    from framework.services.stimulus_service import StimulusService
    body = request.get_json(silent=True) or {}  # type: ignore[attr-defined]
    svc = StimulusService()
    try:
        result = svc.trigger(
            name,
            stimulus_path=body.get("stimulus_path", ""),
            payload=body.get("payload"),
        )
        return jsonify(
            name=name, status=result.status,
            message=result.message, response=result.response,
        )
    except Exception as e:
        return jsonify(error=str(e)), 400


# =========================================================================
# 构建管理 API
# =========================================================================


@app.route("/api/builds", methods=["GET"])
def api_builds_list():
    from framework.services.build_service import BuildService
    svc = BuildService()
    return jsonify(builds=svc.list_all())


@app.route("/api/builds/<name>", methods=["GET"])
def api_builds_get(name: str):
    from framework.services.build_service import BuildService
    svc = BuildService()
    spec = svc.get(name)
    if spec is None:
        return jsonify(error="构建配置不存在"), 404
    return jsonify(build=asdict(spec))


@app.route("/api/builds", methods=["POST"])
def api_builds_add():
    from framework.core.models import BuildSpec
    from framework.services.build_service import BuildService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    spec = BuildSpec(
        name=name, repo_name=body.get("repo_name", ""),
        setup_cmd=body.get("setup_cmd", ""),
        build_cmd=body.get("build_cmd", ""),
        clean_cmd=body.get("clean_cmd", ""),
        output_dir=body.get("output_dir", ""),
    )
    svc = BuildService()
    entry = svc.register(spec)
    return jsonify(message=f"构建已注册: {name}", build=entry)


@app.route("/api/builds/<name>", methods=["DELETE"])
def api_builds_delete(name: str):
    from framework.services.build_service import BuildService
    svc = BuildService()
    if svc.remove(name):
        return jsonify(message=f"构建已删除: {name}")
    return jsonify(error="构建配置不存在"), 404


@app.route("/api/builds/<name>/run", methods=["POST"])
def api_builds_run(name: str):
    from framework.services.build_service import BuildService
    body = request.get_json(silent=True) or {}  # type: ignore[attr-defined]
    svc = BuildService()
    try:
        result = svc.build(
            name,
            work_dir=body.get("work_dir", ""),
            repo_ref=body.get("repo_ref", ""),
            force=body.get("force", False),
        )
        return jsonify(
            name=name, status=result.status,
            duration=result.duration, output_path=result.output_path,
            message=result.message, cached=result.cached,
            repo_ref=result.repo_ref,
        )
    except Exception as e:
        return jsonify(error=str(e)), 400


# =========================================================================
# 结果管理 API（增强）
# =========================================================================


@app.route("/api/results/compare", methods=["GET"])
def api_results_compare():
    from framework.services.result_service import ResultService
    run_a = request.args.get("run_a", "")
    run_b = request.args.get("run_b", "")
    if not run_a or not run_b:
        return jsonify(error="需要提供 run_a 和 run_b"), 400
    svc = ResultService()
    return jsonify(svc.compare_runs(run_a, run_b))


@app.route("/api/results/export", methods=["POST"])
def api_results_export():
    from framework.services.result_service import ResultService
    body = request.get_json(silent=True) or {}
    svc = ResultService()
    path = svc.export(fmt=body.get("format", "html"))
    return jsonify(message="报告已生成", path=path)


@app.route("/api/results/upload", methods=["POST"])
def api_results_upload():
    from framework.services.result_service import ResultService, StorageConfig
    body = request.get_json(silent=True) or {}
    cfg = StorageConfig.from_dict(body.get("storage", {}))
    svc = ResultService()
    result = svc.upload(config=cfg, run_id=body.get("run_id", ""))
    return jsonify(result)


# =========================================================================
# 编排执行 API
# =========================================================================


@app.route("/api/orchestrate", methods=["POST"])
def api_orchestrate():
    from framework.services.execution_orchestrator import (
        ExecutionOrchestrator,
        OrchestrationPlan,
    )
    body = request.get_json(silent=True) or {}
    plan = OrchestrationPlan(
        suite=body.get("suite", "default"),
        config_path=body.get("config_path", "configs/default.yml"),
        parallel=body.get("parallel", 1),
        build_env_name=body.get("build_env_name", ""),
        exe_env_name=body.get("exe_env_name", ""),
        environment=body.get("environment", ""),
        repo_names=body.get("repo_names", []),
        repo_ref_overrides=body.get("repo_ref_overrides", {}),
        build_names=body.get("build_names", []),
        stimulus_names=body.get("stimulus_names", []),
        params=body.get("params", {}),
        snapshot_id=body.get("snapshot_id", ""),
        case_names=body.get("case_names", []),
    )
    orch = ExecutionOrchestrator()
    report = orch.run(plan)
    sr = report.suite_result
    return jsonify(
        success=report.success,
        run_id=report.run_id,
        steps=report.steps,
        suite_result={
            "total": sr.total, "passed": sr.passed,
            "failed": sr.failed, "errors": sr.errors,
        } if sr else None,
    )


def run_server(port: int = 8888, debug: bool = False, host: str = "127.0.0.1") -> None:
    logger.info("aieffect 看板已启动: http://%s:%d", host, port)
    app.run(host=host, port=port, debug=debug)
