"""Web 层统一响应辅助函数

消除各 Blueprint 和 app.py 中重复的 jsonify(error=...), 400/404 模式。
"""

from __future__ import annotations

from flask import Response, jsonify


def ok(data: dict, status: int = 200) -> tuple[Response, int] | Response:
    """成功响应"""
    if status == 200:
        return jsonify(data)
    return jsonify(data), status


def not_found(resource: str) -> tuple[Response, int]:
    """资源不存在"""
    return jsonify(error=f"{resource}不存在"), 404


def bad_request(message: str) -> tuple[Response, int]:
    """请求参数错误"""
    return jsonify(error=message), 400
