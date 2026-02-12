"""激励管理 API Blueprint"""

from __future__ import annotations

from dataclasses import asdict

from flask import Blueprint, Response, jsonify, request

from framework.core.exceptions import AIEffectError

stimuli_bp = Blueprint("stimuli", __name__, url_prefix="/api/stimuli")


def _stimulus_svc():  # type: ignore[no-untyped-def]
    from framework.services.container import get_container
    return get_container().stimulus


@stimuli_bp.route("", methods=["GET"])
def list_all() -> Response:
    return jsonify(stimuli=_stimulus_svc().list_all())


@stimuli_bp.route("/<name>", methods=["GET"])
def get(name: str) -> tuple[Response, int] | Response:
    spec = _stimulus_svc().get(name)
    if spec is None:
        return jsonify(error="激励不存在"), 404
    return jsonify(stimulus=asdict(spec))


@stimuli_bp.route("", methods=["POST"])
def add() -> Response:
    from framework.core.models import RepoSpec, StimulusSpec
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    repo = None
    if body.get("repo"):
        r = body["repo"]
        repo = RepoSpec(
            name=r.get("name", name), url=r.get("url", ""),
            ref=r.get("ref", "main"),
        )
    spec = StimulusSpec(
        name=name, source_type=body.get("source_type", "repo"),
        repo=repo, generator_cmd=body.get("generator_cmd", ""),
        storage_key=body.get("storage_key", ""),
        external_url=body.get("external_url", ""),
        description=body.get("description", ""),
        params=body.get("params", {}),
        template=body.get("template", ""),
    )
    entry = _stimulus_svc().register(spec)
    return jsonify(message=f"激励已注册: {name}", stimulus=entry)


@stimuli_bp.route("/<name>", methods=["DELETE"])
def delete(name: str) -> tuple[Response, int] | Response:
    if _stimulus_svc().remove(name):
        return jsonify(message=f"激励已删除: {name}")
    return jsonify(error="激励不存在"), 404


@stimuli_bp.route("/<name>/acquire", methods=["POST"])
def acquire(name: str) -> tuple[Response, int] | Response:
    try:
        art = _stimulus_svc().acquire(name)
        return jsonify(
            name=name, status=art.status,
            local_path=art.local_path, checksum=art.checksum,
        )
    except AIEffectError as e:
        return jsonify(error=str(e)), 400


@stimuli_bp.route("/<name>/construct", methods=["POST"])
def construct(name: str) -> tuple[Response, int] | Response:
    body = request.get_json(silent=True) or {}
    try:
        art = _stimulus_svc().construct(name, params=body.get("params"))
        return jsonify(
            name=name, status=art.status,
            local_path=art.local_path, checksum=art.checksum,
        )
    except AIEffectError as e:
        return jsonify(error=str(e)), 400


# ---- 结果激励 ----

@stimuli_bp.route("/result", methods=["GET"])
def result_list() -> Response:
    return jsonify(result_stimuli=_stimulus_svc().list_result_stimuli())


@stimuli_bp.route("/result", methods=["POST"])
def result_add() -> tuple[Response, int] | Response:
    from framework.core.models import ResultStimulusSpec
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    spec = ResultStimulusSpec(
        name=name,
        source_type=body.get("source_type", "api"),
        api_url=body.get("api_url", ""),
        api_token=body.get("api_token", ""),
        binary_path=body.get("binary_path", ""),
        parser_cmd=body.get("parser_cmd", ""),
        description=body.get("description", ""),
    )
    entry = _stimulus_svc().register_result_stimulus(spec)
    return jsonify(message=f"结果激励已注册: {name}", result_stimulus=entry)


@stimuli_bp.route("/result/<name>/collect", methods=["POST"])
def result_collect(name: str) -> tuple[Response, int] | Response:
    try:
        art = _stimulus_svc().collect_result_stimulus(name)
        return jsonify(
            name=name, status=art.status,
            local_path=art.local_path, data=art.data,
        )
    except AIEffectError as e:
        return jsonify(error=str(e)), 400


# ---- 触发器 ----

@stimuli_bp.route("/triggers", methods=["GET"])
def triggers_list() -> Response:
    return jsonify(triggers=_stimulus_svc().list_triggers())


@stimuli_bp.route("/triggers", methods=["POST"])
def triggers_add() -> tuple[Response, int] | Response:
    from framework.core.models import TriggerSpec
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    if not name:
        return jsonify(error="需要提供 name"), 400
    spec = TriggerSpec(
        name=name,
        trigger_type=body.get("trigger_type", "api"),
        api_url=body.get("api_url", ""),
        api_token=body.get("api_token", ""),
        binary_cmd=body.get("binary_cmd", ""),
        stimulus_name=body.get("stimulus_name", ""),
        description=body.get("description", ""),
    )
    entry = _stimulus_svc().register_trigger(spec)
    return jsonify(message=f"触发器已注册: {name}", trigger=entry)


@stimuli_bp.route("/triggers/<name>/fire", methods=["POST"])
def triggers_fire(name: str) -> tuple[Response, int] | Response:
    body = request.get_json(silent=True) or {}
    try:
        result = _stimulus_svc().trigger(
            name,
            stimulus_path=body.get("stimulus_path", ""),
            payload=body.get("payload"),
        )
        return jsonify(
            name=name, status=result.status,
            message=result.message, response=result.response,
        )
    except AIEffectError as e:
        return jsonify(error=str(e)), 400
