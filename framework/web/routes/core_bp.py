"""核心 API Blueprint

职责:
- 结果列表查询
- 依赖包列表
- 依赖包上传
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

core_bp = Blueprint("core", __name__, url_prefix="/api")


def _validate_safe_name(value: str, field: str) -> str:
    """验证安全的名称字符串"""
    import re
    _SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")
    value = str(value).strip()
    if not _SAFE_NAME_RE.match(value):
        raise ValueError(f"参数 '{field}' 包含非法字符: {value}")
    return value


@core_bp.route("/results")
def api_results():
    """获取所有执行结果"""
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


@core_bp.route("/deps")
def api_deps():
    """获取依赖包列表"""
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


@core_bp.route("/deps/upload", methods=["POST"])
def api_upload_dep():
    """上传依赖包"""
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
