"""用例管理 API Blueprint

职责:
- 用例 CRUD 操作
- 用例列表查询（支持过滤）
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

cases_bp = Blueprint("cases", __name__, url_prefix="/api/cases")


@cases_bp.route("", methods=["GET"])
def api_cases_list():
    """获取用例列表"""
    from framework.core.case_manager import CaseManager
    cm = CaseManager()
    return jsonify(cases=cm.list_cases(
        tag=request.args.get("tag"),
        environment=request.args.get("environment"),
    ))


@cases_bp.route("/<name>", methods=["GET"])
def api_cases_get(name: str):
    """获取单个用例"""
    from framework.core.case_manager import CaseManager
    case = CaseManager().get_case(name)
    if case is None:
        return jsonify(error="用例不存在"), 404
    return jsonify(case=case)


@cases_bp.route("", methods=["POST"])
def api_cases_add():
    """添加新用例"""
    from framework.core.case_manager import CaseManager
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    cmd = body.get("cmd", "")
    if not name or not cmd:
        return jsonify(error="需要提供 name 和 cmd"), 400
    case = CaseManager().add_case(
        name, cmd,
        description=body.get("description", ""),
        tags=body.get("tags", []),
        timeout=body.get("timeout", 3600),
        environments=body.get("environments", []),
    )
    return jsonify(message=f"用例已保存: {name}", case={"name": name, **case})


@cases_bp.route("/<name>", methods=["PUT"])
def api_cases_update(name: str):
    """更新用例"""
    from framework.core.case_manager import CaseManager
    body = request.get_json(silent=True) or {}
    updated = CaseManager().update_case(name, **body)
    if updated is None:
        return jsonify(error="用例不存在"), 404
    return jsonify(message=f"用例已更新: {name}", case=updated)


@cases_bp.route("/<name>", methods=["DELETE"])
def api_cases_delete(name: str):
    """删除用例"""
    from framework.core.case_manager import CaseManager
    if CaseManager().remove_case(name):
        return jsonify(message=f"用例已删除: {name}")
    return jsonify(error="用例不存在"), 404
