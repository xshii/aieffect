"""构建管理 API Blueprint"""

from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, request

builds_bp = Blueprint("builds", __name__, url_prefix="/api/builds")


@builds_bp.route("", methods=["GET"])
def list_all():
    from framework.services.build_service import BuildService
    return jsonify(builds=BuildService().list_all())


@builds_bp.route("/<name>", methods=["GET"])
def get(name: str):
    from framework.services.build_service import BuildService
    spec = BuildService().get(name)
    if spec is None:
        return jsonify(error="构建配置不存在"), 404
    return jsonify(build=asdict(spec))


@builds_bp.route("", methods=["POST"])
def add():
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
    entry = BuildService().register(spec)
    return jsonify(message=f"构建已注册: {name}", build=entry)


@builds_bp.route("/<name>", methods=["DELETE"])
def delete(name: str):
    from framework.services.build_service import BuildService
    if BuildService().remove(name):
        return jsonify(message=f"构建已删除: {name}")
    return jsonify(error="构建配置不存在"), 404


@builds_bp.route("/<name>/run", methods=["POST"])
def run(name: str):
    from framework.services.build_service import BuildService
    body = request.get_json(silent=True) or {}
    try:
        result = BuildService().build(
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
