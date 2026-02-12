#!/bin/bash
# 代码质量和架构分析工具集
# 自动运行所有静态和动态分析工具

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 创建报告目录
REPORT_DIR="./analysis_reports"
mkdir -p "$REPORT_DIR"

echo "========================================="
echo "  代码质量和架构分析工具"
echo "========================================="
echo ""

# 1. Ruff - 代码风格检查
echo -e "${YELLOW}[1/7] 运行 Ruff 代码风格检查...${NC}"
ruff check framework/ tests/ --output-format=grouped > "$REPORT_DIR/ruff_report.txt" 2>&1 || true
if [ -s "$REPORT_DIR/ruff_report.txt" ]; then
    echo -e "${RED}  ✗ 发现代码风格问题${NC}"
else
    echo -e "${GREEN}  ✓ 代码风格检查通过${NC}"
fi
echo ""

# 2. MyPy - 类型检查
echo -e "${YELLOW}[2/7] 运行 MyPy 类型检查...${NC}"
mypy framework/ --ignore-missing-imports --no-error-summary > "$REPORT_DIR/mypy_report.txt" 2>&1 || true
TYPE_ERRORS=$(grep -c "error:" "$REPORT_DIR/mypy_report.txt" || echo "0")
if [ "$TYPE_ERRORS" -gt 0 ]; then
    echo -e "${RED}  ✗ 发现 $TYPE_ERRORS 个类型问题${NC}"
else
    echo -e "${GREEN}  ✓ 类型检查通过${NC}"
fi
echo ""

# 3. Pylint - 代码质量检查
echo -e "${YELLOW}[3/7] 运行 Pylint 代码质量检查...${NC}"
pylint framework/ --output-format=text --reports=y --score=y > "$REPORT_DIR/pylint_report.txt" 2>&1 || true
PYLINT_SCORE=$(grep "Your code has been rated" "$REPORT_DIR/pylint_report.txt" | grep -oP '\d+\.\d+' | head -1 || echo "0")
echo -e "${GREEN}  评分: $PYLINT_SCORE/10${NC}"
echo ""

# 4. Bandit - 安全检查
echo -e "${YELLOW}[4/7] 运行 Bandit 安全扫描...${NC}"
bandit -r framework/ -f txt -o "$REPORT_DIR/bandit_report.txt" 2>&1 || true
SECURITY_ISSUES=$(grep -c "Issue:" "$REPORT_DIR/bandit_report.txt" || echo "0")
if [ "$SECURITY_ISSUES" -gt 0 ]; then
    echo -e "${YELLOW}  ⚠ 发现 $SECURITY_ISSUES 个潜在安全问题${NC}"
else
    echo -e "${GREEN}  ✓ 未发现安全问题${NC}"
fi
echo ""

# 5. Radon - 复杂度分析
echo -e "${YELLOW}[5/7] 运行 Radon 代码复杂度分析...${NC}"
radon cc framework/ -a -s > "$REPORT_DIR/radon_cc_report.txt" 2>&1 || true
HIGH_COMPLEXITY=$(grep -E " - [C-F] \(" "$REPORT_DIR/radon_cc_report.txt" | wc -l || echo "0")
if [ "$HIGH_COMPLEXITY" -gt 0 ]; then
    echo -e "${YELLOW}  ⚠ 发现 $HIGH_COMPLEXITY 个高复杂度函数${NC}"
else
    echo -e "${GREEN}  ✓ 代码复杂度良好${NC}"
fi
echo ""

# 6. Radon - 可维护性指数
echo -e "${YELLOW}[6/7] 运行 Radon 可维护性分析...${NC}"
radon mi framework/ -s > "$REPORT_DIR/radon_mi_report.txt" 2>&1 || true
LOW_MAINTAINABILITY=$(grep -E " - [C-F] \(" "$REPORT_DIR/radon_mi_report.txt" | wc -l || echo "0")
if [ "$LOW_MAINTAINABILITY" -gt 0 ]; then
    echo -e "${YELLOW}  ⚠ 发现 $LOW_MAINTAINABILITY 个低可维护性文件${NC}"
else
    echo -e "${GREEN}  ✓ 代码可维护性良好${NC}"
fi
echo ""

# 7. Vulture - 死代码检测
echo -e "${YELLOW}[7/7] 运行 Vulture 死代码检测...${NC}"
vulture framework/ --min-confidence 80 > "$REPORT_DIR/vulture_report.txt" 2>&1 || true
DEAD_CODE=$(wc -l < "$REPORT_DIR/vulture_report.txt" || echo "0")
if [ "$DEAD_CODE" -gt 1 ]; then
    echo -e "${YELLOW}  ⚠ 发现可能的死代码${NC}"
else
    echo -e "${GREEN}  ✓ 未发现死代码${NC}"
fi
echo ""

# 8. Pytest - 单元测试（可选）
if [ "$1" == "--with-tests" ]; then
    echo -e "${YELLOW}[额外] 运行 Pytest 测试...${NC}"
    pytest tests/ -v --tb=short > "$REPORT_DIR/pytest_report.txt" 2>&1 || true
    TESTS_PASSED=$(grep -c "PASSED" "$REPORT_DIR/pytest_report.txt" || echo "0")
    TESTS_FAILED=$(grep -c "FAILED" "$REPORT_DIR/pytest_report.txt" || echo "0")
    echo -e "${GREEN}  通过: $TESTS_PASSED${NC} | ${RED}失败: $TESTS_FAILED${NC}"
    echo ""
fi

# 生成汇总报告
echo "========================================="
echo "  分析完成！"
echo "========================================="
echo ""
echo "详细报告保存在: $REPORT_DIR/"
echo ""
echo "文件列表:"
echo "  - ruff_report.txt          (代码风格)"
echo "  - mypy_report.txt          (类型检查)"
echo "  - pylint_report.txt        (代码质量)"
echo "  - bandit_report.txt        (安全扫描)"
echo "  - radon_cc_report.txt      (复杂度分析)"
echo "  - radon_mi_report.txt      (可维护性)"
echo "  - vulture_report.txt       (死代码检测)"
if [ "$1" == "--with-tests" ]; then
    echo "  - pytest_report.txt        (测试结果)"
fi
echo ""
echo "使用 'cat $REPORT_DIR/<文件名>' 查看详细报告"
echo ""

# 显示快速摘要
echo "========================================="
echo "  快速摘要"
echo "========================================="
echo "Pylint评分:     $PYLINT_SCORE/10"
echo "类型错误:       $TYPE_ERRORS"
echo "安全问题:       $SECURITY_ISSUES"
echo "高复杂度函数:   $HIGH_COMPLEXITY"
echo "低可维护性文件: $LOW_MAINTAINABILITY"
echo "========================================="
