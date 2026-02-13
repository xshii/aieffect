"""代码仓 API Blueprint"""

from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, Response, jsonify, request

from framework.web.responses import bad_request, not_found

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
        return not_found("代码仓")
    return jsonify(repo=asdict(spec))


@repos_bp.route("", methods=["POST"])
def add() -> Response:
    body = request.get_json(silent=True) or {}
    if not body.get("name"):
        return bad_request("需要提供 name")
    svc = _repo_svc()
    entry = svc.register(svc.create_spec(body))
    return jsonify(message=f"代码仓已注册: {body['name']}", repo=entry)


@repos_bp.route("/<name>", methods=["DELETE"])
def delete(name: str) -> tuple[Response, int] | Response:
    if _repo_svc().remove(name):
        return jsonify(message=f"代码仓已删除: {name}")
    return not_found("代码仓")


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
