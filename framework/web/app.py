"""轻量级 Web 看板（基于 Flask）

提供：回归结果查看、依赖包状态、上传依赖包、
      用例表单管理、执行历史、日志检查、资源状态、外部结果录入、
      存储对接、环境管理、激励管理、构建管理、结果管理、编排执行。

Blueprint 拆分:
  envs_bp     — /api/envs/**     (13 routes)
  stimuli_bp  — /api/stimuli/**  (13 routes)
  builds_bp   — /api/builds/**   (5 routes)
  repos_bp    — /api/repos/**    (6 routes)

所有路由统一通过 g.svc（Flask 请求级依赖注入）访问服务容器。

启动方式: aieffect dashboard --port 8888
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml
from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

from framework.services.container import get_container
from framework.web.responses import bad_request, not_found
from framework.web.blueprints.builds_bp import builds_bp
from framework.web.blueprints.envs_bp import envs_bp
from framework.web.blueprints.repos_bp import repos_bp
from framework.web.blueprints.stimuli_bp import stimuli_bp

logger = logging.getLogger(__name__)

MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100 MB

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH

# 注册 Blueprint
app.register_blueprint(envs_bp)
app.register_blueprint(stimuli_bp)
app.register_blueprint(builds_bp)
app.register_blueprint(repos_bp)


@app.before_request
def _inject_services() -> None:
    """每次请求前将服务容器注入 Flask g 对象（依赖注入）"""
    g.svc = get_container()


# =========================================================================
# 全局 JSON 错误处理
# =========================================================================


def _safe_int(value: Any, default: int, lo: int = 1, hi: int = 10000) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(n, hi))


_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_safe_name(value: str, field: str) -> str:
    value = str(value).strip()
    if not _SAFE_NAME_RE.match(value):
        from framework.core.exceptions import ValidationError
        raise ValidationError(f"参数 '{field}' 包含非法字符: {value}")
    return value


@app.errorhandler(HTTPException)
def handle_http_exception(exc):
    return jsonify(error=exc.description), exc.code


# 域异常 → 4xx
from framework.core.exceptions import AIEffectError, CaseNotFoundError, ValidationError  # noqa: E402


@app.errorhandler(CaseNotFoundError)
def handle_not_found_error(exc):
    return jsonify(error=str(exc)), 404


@app.errorhandler(ValidationError)
def handle_validation_error(exc):
    return jsonify(error=str(exc)), 400


@app.errorhandler(AIEffectError)
def handle_domain_error(exc):
    return jsonify(error=str(exc)), 400


@app.errorhandler(Exception)
def handle_generic_exception(exc):  # noqa: ARG001
    logger.exception("未处理的异常")
    return jsonify(error="服务器内部错误"), 500


@app.route("/")
def index():
    return render_template("dashboard.html")


# =========================================================================
# 核心 API（结果、依赖、上传）
# =========================================================================


@app.route("/api/results")
def api_results():
    result_dir = Path(g.svc.config.result_dir)
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
    manifest = Path(g.svc.config.manifest)
    if not manifest.exists():
        return jsonify(packages=[])
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    packages = []
    for name, info in (data.get("packages") or {}).items():
        if info:
            packages.append({"name": name, **info})
    return jsonify(packages=packages)


@app.route("/api/deps/upload", methods=["POST"])
def api_upload_dep():
    name = request.form.get("name", "")
    version = request.form.get("version", "")
    file = request.files.get("file")
    if not name or not version or not file or not file.filename:
        return bad_request("需要提供 name、version 和 file")
    name = _validate_safe_name(name, "name")
    version = _validate_safe_name(version, "version")
    safe_name = secure_filename(file.filename)
    if not safe_name:
        return bad_request("文件名不合法")
    base_dir = Path("deps/packages").resolve()
    upload_dir = (base_dir / name / version).resolve()
    if not str(upload_dir).startswith(str(base_dir)):
        return bad_request("路径不合法")
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
    return jsonify(cases=g.svc.cases.list_cases(
        tag=request.args.get("tag"),
        environment=request.args.get("environment"),
    ))


@app.route("/api/cases/<name>", methods=["GET"])
def api_cases_get(name: str):
    case = g.svc.cases.get_case(name)
    if case is None:
        return not_found("用例")
    return jsonify(case=case)


@app.route("/api/cases", methods=["POST"])
def api_cases_add():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    cmd = body.get("cmd", "")
    if not name or not cmd:
        return bad_request("需要提供 name 和 cmd")
    case = g.svc.cases.add_case(
        name, cmd,
        description=body.get("description", ""),
        tags=body.get("tags", []),
        timeout=body.get("timeout", 3600),
        environments=body.get("environments", []),
    )
    return jsonify(message=f"用例已保存: {name}", case={"name": name, **case})


@app.route("/api/cases/<name>", methods=["PUT"])
def api_cases_update(name: str):
    body = request.get_json(silent=True) or {}
    updated = g.svc.cases.update_case(name, **body)
    if updated is None:
        return not_found("用例")
    return jsonify(message=f"用例已更新: {name}", case=updated)


@app.route("/api/cases/<name>", methods=["DELETE"])
def api_cases_delete(name: str):
    if g.svc.cases.remove_case(name):
        return jsonify(message=f"用例已删除: {name}")
    return not_found("用例")


# =========================================================================
# 快照 / 历史 / 日志 / 资源 / 存储
# =========================================================================


@app.route("/api/snapshots", methods=["GET"])
def api_snapshots_list():
    return jsonify(snapshots=g.svc.snapshots.list_snapshots())


@app.route("/api/snapshots", methods=["POST"])
def api_snapshots_create():
    body = request.get_json(silent=True) or {}
    snap = g.svc.snapshots.create(
        description=body.get("description", ""),
        snapshot_id=body.get("id"),
    )
    return jsonify(message=f"快照已创建: {snap['id']}", snapshot=snap)


@app.route("/api/snapshots/<snapshot_id>", methods=["GET"])
def api_snapshots_get(snapshot_id: str):
    snap = g.svc.snapshots.get(snapshot_id)
    if snap is None:
        return not_found("快照")
    return jsonify(snapshot=snap)


@app.route("/api/snapshots/<snapshot_id>/restore", methods=["POST"])
def api_snapshots_restore(snapshot_id: str):
    if g.svc.snapshots.restore(snapshot_id):
        return jsonify(message=f"快照已恢复: {snapshot_id}")
    return not_found("快照")


@app.route("/api/history", methods=["GET"])
def api_history_list():
    return jsonify(records=g.svc.history.query(
        suite=request.args.get("suite"),
        environment=request.args.get("environment"),
        case_name=request.args.get("case_name"),
        limit=_safe_int(request.args.get("limit", 50), default=50),
    ))


@app.route("/api/history/case/<case_name>", methods=["GET"])
def api_history_case(case_name: str):
    return jsonify(summary=g.svc.history.case_summary(case_name))


@app.route("/api/history/submit", methods=["POST"])
def api_history_submit():
    body = request.get_json(silent=True) or {}
    if "suite" not in body or "results" not in body:
        return bad_request("需要提供 suite 和 results")
    entry = g.svc.history.submit_external(body)
    return jsonify(message="执行结果已录入", entry=entry)


@app.route("/api/check-log", methods=["POST"])
def api_check_log():
    rules_file = request.args.get("rules", "")
    if rules_file:
        from framework.core.log_checker import LogChecker
        checker = LogChecker(rules_file=rules_file)
    else:
        checker = g.svc.log_checker
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
        return bad_request("需要提供日志文件或 text 字段")
    report = checker.check_text(text, source=source)
    return jsonify(
        success=report.success,
        log_source=report.log_source,
        total_rules=report.total_rules,
        passed_rules=report.passed_rules,
        failed_rules=report.failed_rules,
        details=[asdict(d) for d in report.details],
    )


@app.route("/api/resource", methods=["GET"])
def api_resource_status():
    return jsonify(asdict(g.svc.resources.status()))


@app.route("/api/storage/<namespace>", methods=["GET"])
def api_storage_list(namespace: str):
    namespace = _validate_safe_name(namespace, "namespace")
    from framework.core.storage import create_storage
    return jsonify(namespace=namespace, keys=create_storage().list_keys(namespace))


@app.route("/api/storage/<namespace>/<key>", methods=["GET"])
def api_storage_get(namespace: str, key: str):
    namespace = _validate_safe_name(namespace, "namespace")
    key = _validate_safe_name(key, "key")
    from framework.core.storage import create_storage
    data = create_storage().get(namespace, key)
    if data is None:
        return not_found("数据")
    return jsonify(data=data)


@app.route("/api/storage/<namespace>/<key>", methods=["PUT"])
def api_storage_put(namespace: str, key: str):
    namespace = _validate_safe_name(namespace, "namespace")
    key = _validate_safe_name(key, "key")
    from framework.core.storage import create_storage
    body = request.get_json(silent=True) or {}
    path = create_storage().put(namespace, key, body)
    return jsonify(message="已存储", path=path)


# =========================================================================
# 结果管理 API（增强）
# =========================================================================


@app.route("/api/results/compare", methods=["GET"])
def api_results_compare():
    run_a = request.args.get("run_a", "")
    run_b = request.args.get("run_b", "")
    if not run_a or not run_b:
        return bad_request("需要提供 run_a 和 run_b")
    return jsonify(g.svc.result.compare_runs(run_a, run_b))


@app.route("/api/results/export", methods=["POST"])
def api_results_export():
    body = request.get_json(silent=True) or {}
    path = g.svc.result.export(fmt=body.get("format", "html"))
    return jsonify(message="报告已生成", path=path)


@app.route("/api/results/upload", methods=["POST"])
def api_results_upload():
    from framework.services.result_service import StorageConfig
    body = request.get_json(silent=True) or {}
    cfg = StorageConfig.from_dict(body.get("storage", {}))
    result = g.svc.result.upload(config=cfg, run_id=body.get("run_id", ""))
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
    report = ExecutionOrchestrator(container=g.svc).run(plan)
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
    import os
    from framework.utils.logger import setup_logging
    setup_logging(
        level=os.getenv("AIEFFECT_LOG_LEVEL", "INFO"),
        json_output=os.getenv("AIEFFECT_LOG_JSON", "") == "1",
    )
    logger.info("aieffect 看板已启动: http://%s:%d", host, port)
    app.run(host=host, port=port, debug=debug)
