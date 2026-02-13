"""编排执行 API Blueprint

职责:
- 7 步编排执行
- 执行报告返回
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

orchestrate_bp = Blueprint("orchestrate", __name__, url_prefix="/api")


@orchestrate_bp.route("/orchestrate", methods=["POST"])
def api_orchestrate():
    """执行 7 步编排流程"""
    from framework.services.execution_orchestrator import (
        ExecutionOrchestrator,
        OrchestrationPlan,
    )
    body = request.get_json(silent=True) or {}
    plan = OrchestrationPlan(
        suite=body.get("suite", "default"),
        config_path=body.get("config_path", "configs/default.yml"),
        parallel=body.get("parallel", 1),
        build_env_name=body.get("build_env_name", ""),
        exe_env_name=body.get("exe_env_name", ""),
        environment=body.get("environment", ""),
        repo_names=body.get("repo_names", []),
        repo_ref_overrides=body.get("repo_ref_overrides", {}),
        build_names=body.get("build_names", []),
        stimulus_names=body.get("stimulus_names", []),
        params=body.get("params", {}),
        snapshot_id=body.get("snapshot_id", ""),
        case_names=body.get("case_names", []),
    )
    report = ExecutionOrchestrator().run(plan)
    sr = report.suite_result
    return jsonify(
        success=report.success,
        run_id=report.run_id,
        steps=report.steps,
        suite_result={
            "total": sr.total, "passed": sr.passed,
            "failed": sr.failed, "errors": sr.errors,
        } if sr else None,
    )
