"""代码仓 API Blueprint"""

from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, Response, jsonify, request

repos_bp = Blueprint("repos", __name__, url_prefix="/api/repos")


def _repo_svc():  # type: ignore[no-untyped-def]
    from framework.services.container import get_container
    return get_container().repo


@repos_bp.route("", methods=["GET"])
def list_all() -> Response:
    return jsonify(repos=_repo_svc().list_all())


@repos_bp.route("/<name>", methods=["GET"])
def get(name: str) -> tuple[Response, int] | Response:
    spec = _repo_svc().get(name)
    if spec is None:
        return jsonify(error="代码仓不存在"), 404
    return jsonify(repo=asdict(spec))


@repos_bp.route("", methods=["POST"])
def add() -> Response:
    from framework.core.models import RepoSpec
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
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
    entry = _repo_svc().register(spec)
    return jsonify(message=f"代码仓已注册: {name}", repo=entry)


@repos_bp.route("/<name>", methods=["DELETE"])
def delete(name: str) -> tuple[Response, int] | Response:
    if _repo_svc().remove(name):
        return jsonify(message=f"代码仓已删除: {name}")
    return jsonify(error="代码仓不存在"), 404


@repos_bp.route("/<name>/checkout", methods=["POST"])
def checkout(name: str) -> Response:
    body = request.get_json(silent=True) or {}
    ws = _repo_svc().checkout(name, ref_override=body.get("ref", ""))
    return jsonify(
        repo=name, status=ws.status,
        local_path=ws.local_path, commit=ws.commit_sha,
    )


@repos_bp.route("/workspaces", methods=["GET"])
def workspaces() -> Response:
    return jsonify(workspaces=_repo_svc().list_workspaces())
