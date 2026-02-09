"""轻量级 Web 看板

基于 Python 标准库 http.server，零外部依赖。
提供：回归结果查看、依赖包状态、手动触发执行等功能。

启动方式:
    python -m framework.web.app --port 8888
    或: aieffect dashboard --port 8888
"""

from __future__ import annotations

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

RESULT_DIR = Path("results")
DEPS_REGISTRY = Path("deps/registry.yml")


class DashboardHandler(BaseHTTPRequestHandler):
    """轻量级看板 HTTP 请求处理器"""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        routes = {
            "/": self._page_index,
            "/api/results": self._api_results,
            "/api/deps": self._api_deps,
        }

        handler = routes.get(path)
        if handler:
            handler(parse_qs(parsed.query))
        else:
            self._send(404, "text/plain", "404 未找到")

    def _page_index(self, _params: dict) -> None:
        """首页 - 单页看板"""
        html = _build_dashboard_html()
        self._send(200, "text/html; charset=utf-8", html)

    def _api_results(self, _params: dict) -> None:
        """API: 获取回归结果列表"""
        results = []
        if RESULT_DIR.exists():
            for f in sorted(RESULT_DIR.glob("*.json")):
                if f.name == "report.json":
                    continue
                try:
                    results.append(json.loads(f.read_text()))
                except json.JSONDecodeError:
                    pass

        summary = {
            "total": len(results),
            "passed": sum(1 for r in results if r.get("status") == "passed"),
            "failed": sum(1 for r in results if r.get("status") == "failed"),
            "errors": sum(1 for r in results if r.get("status") == "error"),
        }

        self._send_json({"summary": summary, "results": results})

    def _api_deps(self, _params: dict) -> None:
        """API: 获取依赖包列表"""
        try:
            import yaml
            if DEPS_REGISTRY.exists():
                data = yaml.safe_load(DEPS_REGISTRY.read_text()) or {}
                packages = []
                for name, info in (data.get("packages") or {}).items():
                    if info:
                        packages.append({"name": name, **info})
                self._send_json({"packages": packages})
            else:
                self._send_json({"packages": []})
        except Exception as e:
            self._send_json({"error": str(e)})

    def _send(self, code: int, content_type: str, body: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _send_json(self, data: dict) -> None:
        self._send(200, "application/json; charset=utf-8", json.dumps(data, ensure_ascii=False, indent=2))

    def log_message(self, format: str, *args: object) -> None:
        logger.info(format, *args)


def _build_dashboard_html() -> str:
    """构建单页看板 HTML（零依赖，内嵌 CSS/JS）"""
    return """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>aieffect 看板</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, "Microsoft YaHei", monospace; background: #f5f5f5; color: #333; }
  .header { background: #1a1a2e; color: #fff; padding: 1em 2em; }
  .header h1 { font-size: 1.4em; }
  .header span { font-size: 0.85em; opacity: 0.7; }
  .container { max-width: 1200px; margin: 0 auto; padding: 1.5em; }

  .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1em; margin-bottom: 1.5em; }
  .card { background: #fff; border-radius: 8px; padding: 1.2em; box-shadow: 0 1px 3px rgba(0,0,0,0.1); text-align: center; }
  .card .num { font-size: 2em; font-weight: bold; }
  .card .label { font-size: 0.85em; color: #666; margin-top: 0.3em; }
  .card.pass .num { color: #28a745; }
  .card.fail .num { color: #dc3545; }
  .card.error .num { color: #ffc107; }
  .card.total .num { color: #007bff; }

  .section { background: #fff; border-radius: 8px; padding: 1.2em; margin-bottom: 1.5em; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
  .section h2 { font-size: 1.1em; margin-bottom: 0.8em; border-bottom: 2px solid #eee; padding-bottom: 0.4em; }

  table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #eee; }
  th { background: #fafafa; font-weight: 600; }
  .status-passed { color: #28a745; font-weight: bold; }
  .status-failed { color: #dc3545; font-weight: bold; }
  .status-error { color: #ffc107; font-weight: bold; }
  .status-skipped { color: #6c757d; }

  .loading { text-align: center; padding: 2em; color: #999; }
  .refresh-btn { float: right; background: #007bff; color: #fff; border: none; padding: 6px 16px; border-radius: 4px; cursor: pointer; font-size: 0.85em; }
  .refresh-btn:hover { background: #0056b3; }
</style>
</head><body>
<div class="header">
  <h1>aieffect 验证看板</h1>
  <span>AI 芯片验证效率集成平台</span>
</div>
<div class="container">
  <div class="cards" id="summary">
    <div class="card total"><div class="num" id="s-total">-</div><div class="label">总计</div></div>
    <div class="card pass"><div class="num" id="s-passed">-</div><div class="label">通过</div></div>
    <div class="card fail"><div class="num" id="s-failed">-</div><div class="label">失败</div></div>
    <div class="card error"><div class="num" id="s-errors">-</div><div class="label">错误</div></div>
  </div>

  <div class="section">
    <h2>回归结果 <button class="refresh-btn" onclick="loadResults()">刷新</button></h2>
    <div id="results-table"><div class="loading">加载中...</div></div>
  </div>

  <div class="section">
    <h2>依赖包状态</h2>
    <div id="deps-table"><div class="loading">加载中...</div></div>
  </div>
</div>

<script>
async function loadResults() {
  try {
    const resp = await fetch('/api/results');
    const data = await resp.json();
    const s = data.summary;
    document.getElementById('s-total').textContent = s.total;
    document.getElementById('s-passed').textContent = s.passed;
    document.getElementById('s-failed').textContent = s.failed;
    document.getElementById('s-errors').textContent = s.errors;

    if (data.results.length === 0) {
      document.getElementById('results-table').innerHTML = '<div class="loading">暂无结果数据</div>';
      return;
    }

    let html = '<table><tr><th>用例名</th><th>状态</th><th>耗时</th><th>信息</th></tr>';
    for (const r of data.results) {
      const cls = 'status-' + (r.status || 'unknown');
      html += '<tr><td>' + (r.name||'') + '</td><td class="'+cls+'">' + (r.status||'') +
              '</td><td>' + (r.duration ? r.duration.toFixed(1)+'s' : '-') +
              '</td><td>' + (r.message||'').substring(0,100) + '</td></tr>';
    }
    html += '</table>';
    document.getElementById('results-table').innerHTML = html;
  } catch(e) {
    document.getElementById('results-table').innerHTML = '<div class="loading">加载失败: '+e+'</div>';
  }
}

async function loadDeps() {
  try {
    const resp = await fetch('/api/deps');
    const data = await resp.json();
    if (!data.packages || data.packages.length === 0) {
      document.getElementById('deps-table').innerHTML = '<div class="loading">暂无依赖包数据</div>';
      return;
    }
    let html = '<table><tr><th>包名</th><th>负责人</th><th>版本</th><th>来源</th><th>说明</th></tr>';
    for (const p of data.packages) {
      html += '<tr><td>'+p.name+'</td><td>'+(p.owner||'-')+'</td><td>'+(p.version||'-')+
              '</td><td>'+(p.source||'-')+'</td><td>'+(p.description||'')+'</td></tr>';
    }
    html += '</table>';
    document.getElementById('deps-table').innerHTML = html;
  } catch(e) {
    document.getElementById('deps-table').innerHTML = '<div class="loading">加载失败: '+e+'</div>';
  }
}

loadResults();
loadDeps();
// 每 30 秒自动刷新
setInterval(loadResults, 30000);
</script>
</body></html>"""


def run_server(port: int = 8888) -> None:
    """启动看板服务器"""
    server = HTTPServer(("0.0.0.0", port), DashboardHandler)
    logger.info("看板已启动: http://localhost:%d", port)
    print(f"aieffect 看板已启动: http://localhost:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n看板已停止。")
        server.server_close()


if __name__ == "__main__":
    import argparse
    from framework.utils.logger import setup_logging

    parser = argparse.ArgumentParser(description="启动 aieffect 轻量级看板")
    parser.add_argument("--port", type=int, default=8888, help="监听端口")
    args = parser.parse_args()

    setup_logging(level="INFO")
    run_server(port=args.port)
