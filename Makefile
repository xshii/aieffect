.PHONY: help setup lint typecheck test test-cov regression report dashboard clean \
       deploy deploy-remote deploy-stop deploy-status

help: ## 显示帮助
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

setup: ## 安装依赖并配置环境
	python -m pip install -e ".[dev]"
	@echo "安装完成。"

lint: ## 运行代码检查 (ruff)
	ruff check framework/ tests/

typecheck: ## 运行类型检查 (mypy)
	mypy framework/

test: ## 运行框架单元测试
	pytest tests/

test-cov: ## 运行测试并生成覆盖率报告
	pytest tests/ --cov=framework --cov-report=html --cov-report=term

regression: ## 运行回归测试套件
	aieffect run default

report: ## 生成测试报告
	aieffect report results

dashboard: ## 启动轻量级 Web 看板
	aieffect dashboard

deploy: ## 本地一键部署 (gunicorn)
	./deploy.sh

deploy-remote: ## 远程部署 (用法: make deploy-remote TARGET=user@host)
	./deploy.sh --remote $(TARGET)

deploy-stop: ## 停止服务
	./deploy.sh --stop

deploy-status: ## 查看服务状态
	./deploy.sh --status

clean: ## 清理生成的文件
	rm -rf __pycache__ .pytest_cache htmlcov .coverage .mypy_cache .ruff_cache
	rm -rf dist build *.egg-info
	@echo "已清理。"
