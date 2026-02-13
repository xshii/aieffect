"""工具 API Blueprint

职责:
- 日志检查
- 资源状态查询
- 键值存储操作
"""

from __future__ import annotations

import re
from dataclasses import asdict

from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

utils_bp = Blueprint("utils", __name__, url_prefix="/api")


def _validate_safe_name(value: str, field: str) -> str:
    """验证安全的名称字符串"""
    _SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
    value = str(value).strip()
    if not _SAFE_NAME_RE.match(value):
        raise ValueError(f"参数 '{field}' 包含非法字符: {value}")
    return value


@utils_bp.route("/check-log", methods=["POST"])
def api_check_log():
    """检查日志文件"""
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


@utils_bp.route("/resource", methods=["GET"])
def api_resource_status():
    """获取资源状态"""
    from framework.core.resource import ResourceManager
    return jsonify(asdict(ResourceManager().status()))


@utils_bp.route("/storage/<namespace>", methods=["GET"])
def api_storage_list(namespace: str):
    """列出存储命名空间的所有键"""
    try:
        namespace = _validate_safe_name(namespace, "namespace")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    from framework.core.storage import create_storage
    return jsonify(namespace=namespace, keys=create_storage().list_keys(namespace))


@utils_bp.route("/storage/<namespace>/<key>", methods=["GET"])
def api_storage_get(namespace: str, key: str):
    """获取存储的数据"""
    try:
        namespace = _validate_safe_name(namespace, "namespace")
        key = _validate_safe_name(key, "key")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    from framework.core.storage import create_storage
    data = create_storage().get(namespace, key)
    if data is None:
        return jsonify(error="数据不存在"), 404
    return jsonify(data=data)


@utils_bp.route("/storage/<namespace>/<key>", methods=["PUT"])
def api_storage_put(namespace: str, key: str):
    """存储数据"""
    try:
        namespace = _validate_safe_name(namespace, "namespace")
        key = _validate_safe_name(key, "key")
    except ValueError as e:
        return jsonify(error=str(e)), 400
    from framework.core.storage import create_storage
    body = request.get_json(silent=True) or {}
    path = create_storage().put(namespace, key, body)
    return jsonify(message="已存储", path=path)
