"""结果管理增强 API Blueprint

职责:
- 结果对比
- 报告导出
- 结果上传
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

results_bp = Blueprint("results", __name__, url_prefix="/api/results")


@results_bp.route("/compare", methods=["GET"])
def api_results_compare():
    """对比两次执行结果"""
    from framework.services.result_service import ResultService
    run_a = request.args.get("run_a", "")
    run_b = request.args.get("run_b", "")
    if not run_a or not run_b:
        return jsonify(error="需要提供 run_a 和 run_b"), 400
    return jsonify(ResultService().compare_runs(run_a, run_b))


@results_bp.route("/export", methods=["POST"])
def api_results_export():
    """导出测试报告"""
    from framework.services.result_service import ResultService
    body = request.get_json(silent=True) or {}
    path = ResultService().export(fmt=body.get("format", "html"))
    return jsonify(message="报告已生成", path=path)


@results_bp.route("/upload", methods=["POST"])
def api_results_upload():
    """上传结果到远程存储"""
    from framework.services.result_service import ResultService, StorageConfig
    body = request.get_json(silent=True) or {}
    cfg = StorageConfig.from_dict(body.get("storage", {}))
    result = ResultService().upload(config=cfg, run_id=body.get("run_id", ""))
    return jsonify(result)
