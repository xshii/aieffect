"""环境服务 API Blueprint（BuildEnv + ExeEnv）"""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request

from framework.core.exceptions import AIEffectError
from framework.web.responses import bad_request, not_found

envs_bp = Blueprint("envs", __name__, url_prefix="/api/envs")


def _env_svc():  # type: ignore[no-untyped-def]
    return g.svc.env


@envs_bp.route("", methods=["GET"])
def list_all() -> Response:
    return jsonify(environments=_env_svc().list_all())


@envs_bp.route("/build", methods=["GET"])
def build_list() -> Response:
    return jsonify(build_envs=_env_svc().list_build_envs())


@envs_bp.route("/exe", methods=["GET"])
def exe_list() -> Response:
    return jsonify(exe_envs=_env_svc().list_exe_envs())


@envs_bp.route("/build", methods=["POST"])
def build_add() -> tuple[Response, int] | Response:
    body = request.get_json(silent=True) or {}
    if not body.get("name"):
        return bad_request("需要提供 name")
    svc = _env_svc()
    entry = svc.register_build_env(svc.create_build_spec(body))
    return jsonify(message=f"构建环境已注册: {body['name']}", build_env=entry)


@envs_bp.route("/exe", methods=["POST"])
def exe_add() -> tuple[Response, int] | Response:
    body = request.get_json(silent=True) or {}
    if not body.get("name"):
        return bad_request("需要提供 name")
    svc = _env_svc()
    entry = svc.register_exe_env(svc.create_exe_spec(body))
    return jsonify(message=f"执行环境已注册: {body['name']}", exe_env=entry)


@envs_bp.route("/build/<name>", methods=["DELETE"])
def build_delete(name: str) -> tuple[Response, int] | Response:
    if _env_svc().remove_build_env(name):
        return jsonify(message=f"构建环境已删除: {name}")
    return not_found("构建环境")


@envs_bp.route("/exe/<name>", methods=["DELETE"])
def exe_delete(name: str) -> tuple[Response, int] | Response:
    if _env_svc().remove_exe_env(name):
        return jsonify(message=f"执行环境已删除: {name}")
    return not_found("执行环境")


@envs_bp.route("/apply", methods=["POST"])
def apply() -> tuple[Response, int] | Response:
    body = request.get_json(silent=True) or {}
    try:
        session = _env_svc().apply(
            build_env_name=body.get("build_env_name", ""),
            exe_env_name=body.get("exe_env_name", ""),
        )
        return jsonify(
            session_id=session.session_id,
            name=session.name, status=session.status,
            work_dir=session.work_dir,
            variables_count=len(session.resolved_vars),
        )
    except AIEffectError as e:
        return bad_request(str(e))


@envs_bp.route("/sessions", methods=["GET"])
def sessions() -> Response:
    return jsonify(sessions=_env_svc().list_sessions())


@envs_bp.route("/sessions/<session_id>/release", methods=["POST"])
def release(session_id: str) -> tuple[Response, int] | Response:
    svc = _env_svc()
    session = svc.get_session(session_id)
    if session is None:
        return not_found("会话")
    svc.release(session)
    return jsonify(message="环境已释放", session_id=session_id)


@envs_bp.route("/sessions/<session_id>/timeout", methods=["POST"])
def timeout(session_id: str) -> tuple[Response, int] | Response:
    svc = _env_svc()
    session = svc.get_session(session_id)
    if session is None:
        return not_found("会话")
    svc.timeout(session)
    return jsonify(message="环境已超时", session_id=session_id)


@envs_bp.route("/sessions/<session_id>/invalid", methods=["POST"])
def invalid(session_id: str) -> tuple[Response, int] | Response:
    svc = _env_svc()
    session = svc.get_session(session_id)
    if session is None:
        return not_found("会话")
    svc.invalid(session)
    return jsonify(message="环境已失效", session_id=session_id)


@envs_bp.route("/execute", methods=["POST"])
def execute() -> tuple[Response, int] | Response:
    body = request.get_json(silent=True) or {}
    cmd = body.get("cmd", "")
    if not cmd:
        return bad_request("需要提供 cmd")
    svc = _env_svc()
    try:
        session = svc.apply(
            build_env_name=body.get("build_env_name", ""),
            exe_env_name=body.get("exe_env_name", ""),
        )
        result = svc.execute_in(session, cmd, timeout=body.get("timeout", 3600))
        svc.release(session)
        return jsonify(result=result)
    except AIEffectError as e:
        return bad_request(str(e))
