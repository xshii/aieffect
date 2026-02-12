"""构建管理 API Blueprint"""

from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, Response, jsonify, request

from framework.core.exceptions import AIEffectError

builds_bp = Blueprint("builds", __name__, url_prefix="/api/builds")


def _build_svc():  # type: ignore[no-untyped-def]
    from framework.services.container import get_container
    return get_container().build


@builds_bp.route("", methods=["GET"])
def list_all() -> Response:
    return jsonify(builds=_build_svc().list_all())


@builds_bp.route("/<name>", methods=["GET"])
def get(name: str) -> tuple[Response, int] | Response:
    spec = _build_svc().get(name)
    if spec is None:
        return jsonify(error="构建配置不存在"), 404
    return jsonify(build=asdict(spec))


@builds_bp.route("", methods=["POST"])
def add() -> Response:
    from framework.core.models import BuildSpec
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
    entry = _build_svc().register(spec)
    return jsonify(message=f"构建已注册: {name}", build=entry)


@builds_bp.route("/<name>", methods=["DELETE"])
def delete(name: str) -> tuple[Response, int] | Response:
    if _build_svc().remove(name):
        return jsonify(message=f"构建已删除: {name}")
    return jsonify(error="构建配置不存在"), 404


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
        return jsonify(error=str(e)), 400
