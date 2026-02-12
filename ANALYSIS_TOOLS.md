# 代码分析工具使用指南

本项目配置了一套完整的代码质量和架构分析工具，用于确保代码质量、安全性和可维护性。

## 工具列表

### 静态分析工具

1. **Ruff** - 快速Python代码检查工具
   - 检查代码风格和常见问题
   - 替代flake8、isort等工具

2. **MyPy** - 静态类型检查器
   - 验证类型注解
   - 发现类型相关的bug

3. **Pylint** - 全面的代码质量检查器
   - 检查代码风格、错误、重构建议
   - 提供代码评分

4. **Bandit** - 安全漏洞扫描器
   - 检测常见的安全问题
   - 识别潜在的安全漏洞

5. **Radon** - 代码度量工具
   - 计算圈复杂度
   - 评估可维护性指数

6. **Vulture** - 死代码检测器
   - 查找未使用的代码
   - 帮助清理冗余代码

### 动态分析工具

7. **Pytest** - 测试框架
   - 运行单元测试和集成测试
   - 提供代码覆盖率报告

## 快速开始

### 1. 安装工具

```bash
# 安装所有分析工具
pip install ruff mypy pylint bandit radon vulture pytest pytest-cov

# 安装项目依赖
pip install -r requirements.txt  # 如果存在
# 或者
pip install pyyaml click rich junitparser flask types-PyYAML
```

### 2. 运行完整分析

```bash
# 运行所有静态分析工具
./run_analysis.sh

# 运行分析并包含测试
./run_analysis.sh --with-tests
```

### 3. 查看结果

分析报告将保存在 `analysis_reports/` 目录下：
- `err.md` - 完整的分析报告和建议
- `ruff_report.txt` - 代码风格问题
- `mypy_report.txt` - 类型检查结果
- `pylint_report.txt` - 代码质量报告
- `bandit_report.txt` - 安全扫描结果
- `radon_cc_report.txt` - 复杂度分析
- `radon_mi_report.txt` - 可维护性指数
- `vulture_report.txt` - 死代码检测

## 单独运行工具

### Ruff - 代码风格检查
```bash
# 检查代码
ruff check framework/ tests/

# 自动修复问题
ruff check framework/ tests/ --fix

# 格式化代码
ruff format framework/ tests/
```

### MyPy - 类型检查
```bash
# 基本类型检查
mypy framework/

# 包含未类型化的函数
mypy framework/ --check-untyped-defs

# 严格模式
mypy framework/ --strict
```

### Pylint - 代码质量检查
```bash
# 检查整个项目
pylint framework/

# 只显示错误和警告
pylint framework/ --errors-only

# 生成详细报告
pylint framework/ --reports=y
```

### Bandit - 安全扫描
```bash
# 扫描所有代码
bandit -r framework/

# 只显示中高危问题
bandit -r framework/ -ll

# 生成HTML报告
bandit -r framework/ -f html -o security_report.html
```

### Radon - 代码度量
```bash
# 计算圈复杂度
radon cc framework/ -a

# 只显示C级及以上复杂度
radon cc framework/ -nc

# 计算可维护性指数
radon mi framework/

# 计算原始度量
radon raw framework/
```

### Vulture - 死代码检测
```bash
# 检测死代码（置信度80%）
vulture framework/ --min-confidence 80

# 更严格的检测（置信度60%）
vulture framework/ --min-confidence 60
```

### Pytest - 运行测试
```bash
# 运行所有测试
pytest tests/

# 运行特定测试文件
pytest tests/ut/core/test_config.py

# 显示详细输出
pytest tests/ -v

# 生成覆盖率报告
pytest tests/ --cov=framework --cov-report=html

# 只运行失败的测试
pytest tests/ --lf
```

## 集成到开发流程

### Pre-commit Hook

创建 `.git/hooks/pre-commit` 文件：
```bash
#!/bin/bash
# 提交前运行快速检查

echo "运行代码质量检查..."

# Ruff检查
ruff check framework/ || exit 1

# MyPy类型检查（关键文件）
mypy framework/core/ framework/services/ || exit 1

# 运行快速测试
pytest tests/ut/ -x || exit 1

echo "✓ 检查通过"
```

### CI/CD 集成

在CI/CD管道中添加：
```yaml
# GitHub Actions 示例
- name: Run Code Analysis
  run: |
    pip install ruff mypy pylint bandit radon vulture pytest pytest-cov
    ./run_analysis.sh --with-tests

- name: Upload Reports
  uses: actions/upload-artifact@v3
  with:
    name: analysis-reports
    path: analysis_reports/
```

## 配置文件

### pyproject.toml
项目已配置以下工具：
- Ruff: 代码风格规则
- MyPy: 类型检查配置
- Pytest: 测试路径和选项

### .bandit
Bandit安全扫描配置文件，可以调整：
- 排除目录
- 跳过特定测试
- 严重性级别

## 建议的开发工作流

1. **开发阶段**
   - 使用Ruff进行即时代码检查
   - 运行MyPy验证类型注解

2. **提交前**
   - 运行快速分析：`ruff check && mypy framework/`
   - 运行相关测试：`pytest tests/ut/`

3. **PR审查前**
   - 运行完整分析：`./run_analysis.sh --with-tests`
   - 查看err.md中的建议
   - 修复高优先级问题

4. **定期维护**
   - 每周运行完整分析
   - 监控代码质量趋势
   - 重构高复杂度函数

## 度量目标

### 代码质量目标
- Pylint评分：≥ 9.0/10
- 平均复杂度：≤ A级 (5)
- C级复杂度函数：0个
- 类型覆盖率：≥ 80%

### 安全目标
- 高危安全问题：0个
- 中危安全问题：0个
- 低危问题：定期审查

### 测试目标
- 测试通过率：100%
- 代码覆盖率：≥ 70%
- 单元测试覆盖：≥ 80%

## 常见问题

### Q: 如何忽略特定的Pylint警告？
A: 在代码中添加注释：
```python
# pylint: disable=line-too-long
long_line = "very long string..."
```

### Q: 如何忽略Bandit的误报？
A: 添加nosec注释：
```python
subprocess.run(["git", "status"])  # nosec B603
```

### Q: MyPy报告类型存根缺失怎么办？
A: 安装对应的类型包：
```bash
pip install types-PyYAML types-requests
```

### Q: 如何降低函数复杂度？
A: 常见方法：
- 提取子函数
- 使用早期返回
- 拆分复杂条件
- 使用策略模式

## 更多资源

- [Ruff文档](https://docs.astral.sh/ruff/)
- [MyPy文档](https://mypy.readthedocs.io/)
- [Pylint文档](https://pylint.pycqa.org/)
- [Bandit文档](https://bandit.readthedocs.io/)
- [Radon文档](https://radon.readthedocs.io/)
- [Pytest文档](https://docs.pytest.org/)

## 支持

如有问题或建议，请：
1. 查看 `err.md` 中的详细报告
2. 参考各工具的官方文档
3. 在团队中讨论最佳实践
