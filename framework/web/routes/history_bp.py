"""历史记录 API Blueprint

职责:
- 执行历史查询
- 用例执行汇总
- 外部结果录入
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request


def _safe_int(value, default: int, lo: int = 1, hi: int = 10000) -> int:
    """安全解析整数"""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(n, hi))


history_bp = Blueprint("history", __name__, url_prefix="/api/history")


@history_bp.route("", methods=["GET"])
def api_history_list():
    """查询执行历史"""
    from framework.core.history import HistoryManager
    return jsonify(records=HistoryManager().query(
        suite=request.args.get("suite"),
        environment=request.args.get("environment"),
        case_name=request.args.get("case_name"),
        limit=_safe_int(request.args.get("limit", 50), default=50),
    ))


@history_bp.route("/case/<case_name>", methods=["GET"])
def api_history_case(case_name: str):
    """获取用例执行汇总"""
    from framework.core.history import HistoryManager
    return jsonify(summary=HistoryManager().case_summary(case_name))


@history_bp.route("/submit", methods=["POST"])
def api_history_submit():
    """提交外部执行结果"""
    from framework.core.history import HistoryManager
    body = request.get_json(silent=True) or {}
    if "suite" not in body or "results" not in body:
        return jsonify(error="需要提供 suite 和 results"), 400
    try:
        entry = HistoryManager().submit_external(body)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    return jsonify(message="执行结果已录入", entry=entry)
