"""构建管理 API Blueprint"""

from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, Response, g, jsonify, request

from framework.core.exceptions import AIEffectError
from framework.web.responses import bad_request, not_found

builds_bp = Blueprint("builds", __name__, url_prefix="/api/builds")


def _build_svc():  # type: ignore[no-untyped-def]
    return g.svc.build


@builds_bp.route("", methods=["GET"])
def list_all() -> Response:
    return jsonify(builds=_build_svc().list_all())


@builds_bp.route("/<name>", methods=["GET"])
def get(name: str) -> tuple[Response, int] | Response:
    spec = _build_svc().get(name)
    if spec is None:
        return not_found("构建配置")
    return jsonify(build=asdict(spec))


@builds_bp.route("", methods=["POST"])
def add() -> Response:
    body = request.get_json(silent=True) or {}
    if not body.get("name"):
        return bad_request("需要提供 name")
    svc = _build_svc()
    entry = svc.register(svc.create_spec(body))
    return jsonify(message=f"构建已注册: {body['name']}", build=entry)


@builds_bp.route("/<name>", methods=["DELETE"])
def delete(name: str) -> tuple[Response, int] | Response:
    if _build_svc().remove(name):
        return jsonify(message=f"构建已删除: {name}")
    return not_found("构建配置")


@builds_bp.route("/<name>/run", methods=["POST"])
def run(name: str) -> tuple[Response, int] | Response:
    body = request.get_json(silent=True) or {}
    try:
        result = _build_svc().build(
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
    except AIEffectError as e:
        return bad_request(str(e))
