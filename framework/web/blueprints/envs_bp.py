"""环境服务 API Blueprint（BuildEnv + ExeEnv）"""

from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, jsonify, request

envs_bp = Blueprint("envs", __name__, url_prefix="/api/envs")


@envs_bp.route("", methods=["GET"])
def list_all():
    from framework.services.env_service import EnvService
    return jsonify(environments=EnvService().list_all())


@envs_bp.route("/build", methods=["GET"])
def build_list():
    from framework.services.env_service import EnvService
    return jsonify(build_envs=EnvService().list_build_envs())


@envs_bp.route("/exe", methods=["GET"])
def exe_list():
    from framework.services.env_service import EnvService
    return jsonify(exe_envs=EnvService().list_exe_envs())


@envs_bp.route("/build", methods=["POST"])
def build_add():
    from framework.core.models import BuildEnvSpec
    from framework.services.env_service import EnvService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    spec = BuildEnvSpec(
        name=name,
        build_env_type=body.get("build_env_type", "local"),
        description=body.get("description", ""),
        work_dir=body.get("work_dir", ""),
        variables=body.get("variables", {}),
        host=body.get("host", ""),
        port=body.get("port", 22),
        user=body.get("user", ""),
        key_path=body.get("key_path", ""),
    )
    entry = EnvService().register_build_env(spec)
    return jsonify(message=f"构建环境已注册: {name}", build_env=entry)


@envs_bp.route("/exe", methods=["POST"])
def exe_add():
    from framework.core.models import ExeEnvSpec, ToolSpec
    from framework.services.env_service import EnvService
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    tools: dict[str, ToolSpec] = {}
    for tname, tinfo in (body.get("tools") or {}).items():
        ti = tinfo if isinstance(tinfo, dict) else {}
        tools[tname] = ToolSpec(
            name=tname, version=ti.get("version", ""),
            install_path=ti.get("install_path", ""),
            env_vars=ti.get("env_vars", {}),
        )
    spec = ExeEnvSpec(
        name=name,
        exe_env_type=body.get("exe_env_type", "eda"),
        description=body.get("description", ""),
        api_url=body.get("api_url", ""),
        api_token=body.get("api_token", ""),
        variables=body.get("variables", {}),
        tools=tools,
        licenses=body.get("licenses", {}),
        timeout=body.get("timeout", 3600),
        build_env_name=body.get("build_env_name", ""),
    )
    entry = EnvService().register_exe_env(spec)
    return jsonify(message=f"执行环境已注册: {name}", exe_env=entry)


@envs_bp.route("/build/<name>", methods=["DELETE"])
def build_delete(name: str):
    from framework.services.env_service import EnvService
    if EnvService().remove_build_env(name):
        return jsonify(message=f"构建环境已删除: {name}")
    return jsonify(error="构建环境不存在"), 404


@envs_bp.route("/exe/<name>", methods=["DELETE"])
def exe_delete(name: str):
    from framework.services.env_service import EnvService
    if EnvService().remove_exe_env(name):
        return jsonify(message=f"执行环境已删除: {name}")
    return jsonify(error="执行环境不存在"), 404


@envs_bp.route("/apply", methods=["POST"])
def apply():
    from framework.services.env_service import EnvService
    body = request.get_json(silent=True) or {}
    try:
        session = EnvService().apply(
            build_env_name=body.get("build_env_name", ""),
            exe_env_name=body.get("exe_env_name", ""),
        )
        return jsonify(
            session_id=session.session_id,
            name=session.name, status=session.status,
            work_dir=session.work_dir,
            variables_count=len(session.resolved_vars),
        )
    except Exception as e:
        return jsonify(error=str(e)), 400


@envs_bp.route("/sessions", methods=["GET"])
def sessions():
    from framework.services.env_service import EnvService
    return jsonify(sessions=EnvService().list_sessions())


@envs_bp.route("/sessions/<session_id>/release", methods=["POST"])
def release(session_id: str):
    from framework.services.env_service import EnvService
    svc = EnvService()
    session = svc.get_session(session_id)
    if session is None:
        return jsonify(error="会话不存在"), 404
    svc.release(session)
    return jsonify(message="环境已释放", session_id=session_id)


@envs_bp.route("/sessions/<session_id>/timeout", methods=["POST"])
def timeout(session_id: str):
    from framework.services.env_service import EnvService
    svc = EnvService()
    session = svc.get_session(session_id)
    if session is None:
        return jsonify(error="会话不存在"), 404
    svc.timeout(session)
    return jsonify(message="环境已超时", session_id=session_id)


@envs_bp.route("/sessions/<session_id>/invalid", methods=["POST"])
def invalid(session_id: str):
    from framework.services.env_service import EnvService
    svc = EnvService()
    session = svc.get_session(session_id)
    if session is None:
        return jsonify(error="会话不存在"), 404
    svc.invalid(session)
    return jsonify(message="环境已失效", session_id=session_id)


@envs_bp.route("/execute", methods=["POST"])
def execute():
    from framework.services.env_service import EnvService
    body = request.get_json(silent=True) or {}
    cmd = body.get("cmd", "")
    if not cmd:
        return jsonify(error="需要提供 cmd"), 400
    svc = EnvService()
    try:
        session = svc.apply(
            build_env_name=body.get("build_env_name", ""),
            exe_env_name=body.get("exe_env_name", ""),
        )
        result = svc.execute_in(session, cmd, timeout=body.get("timeout", 3600))
        svc.release(session)
        return jsonify(result=result)
    except Exception as e:
        return jsonify(error=str(e)), 400
