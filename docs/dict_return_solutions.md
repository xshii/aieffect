# Dict 返回值的更好替代方案

## 方案对比

| 方案 | 类型安全 | IDE支持 | 运行时验证 | 序列化 | 额外依赖 | 推荐度 |
|------|---------|---------|-----------|--------|---------|-------|
| dict[str, Any] | ❌ | ❌ | ❌ | ✅ | ❌ | ⭐ |
| TypedDict | ✅ | ✅ | ❌ | ✅ | ❌ | ⭐⭐⭐⭐ |
| dataclass | ✅ | ✅ | ❌ | 需手动 | ❌ | ⭐⭐⭐⭐⭐ |
| Pydantic | ✅ | ✅ | ✅ | ✅ | ✅ | ⭐⭐⭐⭐⭐ |
| NamedTuple | ✅ | ✅ | ❌ | 需手动 | ❌ | ⭐⭐⭐ |

---

## 方案1: TypedDict (推荐用于简单场景)

### 优点
- ✅ 静态类型检查（MyPy, Pyright）
- ✅ IDE 自动补全
- ✅ 向后兼容字典（可以直接序列化为 JSON）
- ✅ 无需额外依赖
- ✅ 零运行时开销

### 缺点
- ❌ 运行时没有验证（只是类型提示）
- ❌ 不能添加方法

### 代码示例

```python
from typing import TypedDict, NotRequired

# 定义返回类型
class CompareResult(TypedDict):
    """对比结果"""
    run_a: dict[str, str]
    run_b: dict[str, str]
    diffs: list[dict[str, str]]
    total_cases: int
    changed_cases: int

class CompareError(TypedDict):
    """对比错误"""
    error: str

# 使用联合类型表示可能失败
CompareResponse = CompareResult | CompareError

# 使用示例
def compare_runs(self, run_id_a: str, run_id_b: str) -> CompareResponse:
    """对比两次执行结果"""
    rec_a, rec_b = self._find_records(run_id_a, run_id_b)

    if rec_a is None or rec_b is None:
        return CompareError(error="未找到记录")  # ✅ 类型安全

    diffs, total = self._compute_diffs(rec_a, rec_b, run_id_a, run_id_b)
    return CompareResult(  # ✅ IDE 会检查字段
        run_a={"run_id": run_id_a, "summary": rec_a.get("summary", {})},
        run_b={"run_id": run_id_b, "summary": rec_b.get("summary", {})},
        diffs=diffs,
        total_cases=total,
        changed_cases=len(diffs),
    )

# 调用方
result = service.compare_runs("run1", "run2")
if "error" in result:
    print(f"错误: {result['error']}")  # ✅ IDE 自动补全
else:
    print(f"变更: {result['changed_cases']}")  # ✅ IDE 自动补全
    print(f"差异: {result['diffs']}")  # ✅ 拼写错误会被 IDE 标记
```

### 可选字段支持

```python
from typing import TypedDict, NotRequired

class UploadResult(TypedDict):
    status: str                          # 必填
    type: str                            # 必填
    message: NotRequired[str]            # 可选（Python 3.11+）
    response: NotRequired[dict[str, Any]]  # 可选
    target: NotRequired[str]             # 可选

# Python 3.10 及以下的写法
class UploadResult(TypedDict, total=False):
    message: str
    response: dict[str, Any]
    target: str

class UploadResult(UploadResult, total=True):  # 继承，添加必填字段
    status: str
    type: str
```

---

## 方案2: dataclass (推荐用于复杂场景)

### 优点
- ✅ 静态类型检查
- ✅ IDE 自动补全
- ✅ 可以添加方法
- ✅ 自动生成 `__repr__`, `__eq__`
- ✅ 支持默认值、验证
- ✅ 无需额外依赖

### 缺点
- ❌ 需要手动序列化为字典（但很简单）
- ❌ 运行时没有验证（除非自己写）

### 代码示例

```python
from dataclasses import dataclass, asdict, field
from typing import Any

@dataclass
class RunSummary:
    """单次运行摘要"""
    run_id: str
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return asdict(self)

@dataclass
class CompareResult:
    """对比结果"""
    run_a: RunSummary
    run_b: RunSummary
    diffs: list[dict[str, str]]
    total_cases: int
    changed_cases: int

    def to_dict(self) -> dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "run_a": self.run_a.to_dict(),
            "run_b": self.run_b.to_dict(),
            "diffs": self.diffs,
            "total_cases": self.total_cases,
            "changed_cases": self.changed_cases,
        }

    def has_changes(self) -> bool:
        """是否有变更"""
        return self.changed_cases > 0

    def get_failed_cases(self) -> list[str]:
        """获取失败的用例"""
        return [
            d["case"] for d in self.diffs
            if d.get(self.run_b.run_id) == "failed"
        ]

@dataclass
class CompareError:
    """对比错误"""
    error: str

    def to_dict(self) -> dict[str, str]:
        return {"error": self.error}

# 使用示例
def compare_runs(self, run_id_a: str, run_id_b: str) -> CompareResult | CompareError:
    """对比两次执行结果"""
    rec_a, rec_b = self._find_records(run_id_a, run_id_b)

    if rec_a is None or rec_b is None:
        return CompareError(error="未找到记录")  # ✅ 类型安全

    diffs, total = self._compute_diffs(rec_a, rec_b, run_id_a, run_id_b)
    return CompareResult(  # ✅ IDE 检查字段和类型
        run_a=RunSummary(run_id=run_id_a, summary=rec_a.get("summary", {})),
        run_b=RunSummary(run_id=run_id_b, summary=rec_b.get("summary", {})),
        diffs=diffs,
        total_cases=total,
        changed_cases=len(diffs),
    )

# 调用方
result = service.compare_runs("run1", "run2")
if isinstance(result, CompareError):
    print(f"错误: {result.error}")  # ✅ 属性访问
else:
    print(f"变更: {result.changed_cases}")  # ✅ 属性访问
    print(f"有变更: {result.has_changes()}")  # ✅ 可以调用方法

    # 序列化为 JSON
    import json
    json_str = json.dumps(result.to_dict(), indent=2)
```

### 默认值和工厂函数

```python
from dataclasses import dataclass, field
from typing import Any

@dataclass
class UploadResult:
    status: str
    type: str
    message: str = ""                           # 默认值
    response: dict[str, Any] = field(default_factory=dict)  # 可变默认值
    tags: list[str] = field(default_factory=list)

    def __post_init__(self):
        """初始化后验证"""
        if self.status not in ("success", "error"):
            raise ValueError(f"无效的状态: {self.status}")
```

---

## 方案3: Pydantic BaseModel (推荐用于需要验证的场景)

### 优点
- ✅ 静态类型检查
- ✅ IDE 自动补全
- ✅ **运行时验证**（自动类型转换和验证）
- ✅ 强大的序列化/反序列化
- ✅ 可以添加方法
- ✅ JSON Schema 支持

### 缺点
- ❌ 需要安装 pydantic（额外依赖）
- ❌ 轻微性能开销（验证需要时间）

### 代码示例

```python
from pydantic import BaseModel, Field, field_validator
from typing import Any

class RunSummary(BaseModel):
    """单次运行摘要"""
    run_id: str
    summary: dict[str, Any] = Field(default_factory=dict)

class CompareResult(BaseModel):
    """对比结果"""
    run_a: RunSummary
    run_b: RunSummary
    diffs: list[dict[str, str]]
    total_cases: int = Field(ge=0, description="总用例数")
    changed_cases: int = Field(ge=0, description="变更用例数")

    @field_validator('changed_cases')
    @classmethod
    def validate_changed_cases(cls, v: int, info) -> int:
        """验证变更数不能超过总数"""
        total = info.data.get('total_cases', 0)
        if v > total:
            raise ValueError(f"changed_cases ({v}) 不能大于 total_cases ({total})")
        return v

    def has_changes(self) -> bool:
        """是否有变更"""
        return self.changed_cases > 0

    # ✅ 自动序列化
    def to_json(self) -> str:
        return self.model_dump_json(indent=2)

class CompareError(BaseModel):
    """对比错误"""
    error: str

# 使用示例
def compare_runs(self, run_id_a: str, run_id_b: str) -> CompareResult | CompareError:
    """对比两次执行结果"""
    rec_a, rec_b = self._find_records(run_id_a, run_id_b)

    if rec_a is None or rec_b is None:
        return CompareError(error="未找到记录")  # ✅ 自动验证

    diffs, total = self._compute_diffs(rec_a, rec_b, run_id_a, run_id_b)

    # ✅ 会自动验证类型和约束
    return CompareResult(
        run_a=RunSummary(run_id=run_id_a, summary=rec_a.get("summary", {})),
        run_b=RunSummary(run_id=run_id_b, summary=rec_b.get("summary", {})),
        diffs=diffs,
        total_cases=total,
        changed_cases=len(diffs),
    )

# 调用方
result = service.compare_runs("run1", "run2")
if isinstance(result, CompareError):
    print(f"错误: {result.error}")
else:
    print(f"变更: {result.changed_cases}")  # ✅ 属性访问

    # ✅ 序列化为字典
    dict_result = result.model_dump()

    # ✅ 序列化为 JSON
    json_str = result.model_dump_json(indent=2)

    # ✅ 从字典反序列化
    loaded = CompareResult.model_validate(dict_result)
```

---

## 方案4: NamedTuple (推荐用于不可变数据)

### 优点
- ✅ 静态类型检查
- ✅ IDE 自动补全
- ✅ 不可变（线程安全）
- ✅ 轻量（比 dataclass 更快）
- ✅ 可以作为字典键

### 缺点
- ❌ 不可变（不能修改）
- ❌ 不能有默认值（Python 3.6.1+才支持）

### 代码示例

```python
from typing import NamedTuple

class RunSummary(NamedTuple):
    """单次运行摘要"""
    run_id: str
    summary: dict[str, Any] = {}  # Python 3.6.1+

class CompareResult(NamedTuple):
    """对比结果"""
    run_a: RunSummary
    run_b: RunSummary
    diffs: list[dict[str, str]]
    total_cases: int
    changed_cases: int

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "run_a": {"run_id": self.run_a.run_id, "summary": self.run_a.summary},
            "run_b": {"run_id": self.run_b.run_id, "summary": self.run_b.summary},
            "diffs": self.diffs,
            "total_cases": self.total_cases,
            "changed_cases": self.changed_cases,
        }

# 使用示例
result = CompareResult(
    run_a=RunSummary(run_id="run1", summary={}),
    run_b=RunSummary(run_id="run2", summary={}),
    diffs=[],
    total_cases=10,
    changed_cases=2,
)

# ✅ 不可变
# result.changed_cases = 3  # ❌ AttributeError
```

---

## 推荐方案总结

### 🥇 首选：dataclass（平衡性最好）

```python
from dataclasses import dataclass, asdict

@dataclass
class CompareResult:
    run_a: dict[str, Any]
    run_b: dict[str, Any]
    diffs: list[dict[str, str]]
    total_cases: int
    changed_cases: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
```

**适用场景**：
- ✅ 大多数情况
- ✅ 需要添加方法
- ✅ 需要可修改的对象

---

### 🥈 次选：TypedDict（最小改动）

```python
from typing import TypedDict

class CompareResult(TypedDict):
    run_a: dict[str, Any]
    run_b: dict[str, Any]
    diffs: list[dict[str, str]]
    total_cases: int
    changed_cases: int
```

**适用场景**：
- ✅ 现有代码改动最小
- ✅ 需要向后兼容字典
- ✅ 不需要运行时验证

---

### 🥉 特殊场景：Pydantic（需要验证）

```python
from pydantic import BaseModel, Field

class CompareResult(BaseModel):
    run_a: dict[str, Any]
    run_b: dict[str, Any]
    diffs: list[dict[str, str]]
    total_cases: int = Field(ge=0)
    changed_cases: int = Field(ge=0)
```

**适用场景**：
- ✅ API 输入/输出验证
- ✅ 需要运行时类型检查
- ✅ 需要自动文档生成（OpenAPI）

---

## 迁移策略

### 渐进式迁移（推荐）

1. **第一步**：为现有 dict 返回值添加 TypedDict 类型提示
   ```python
   class CompareResult(TypedDict):
       # 定义字段
       pass

   def compare_runs(...) -> CompareResult:
       return {...}  # 现有代码不变
   ```

2. **第二步**：新功能使用 dataclass
   ```python
   @dataclass
   class NewFeatureResult:
       # 定义字段
       pass

   def new_feature(...) -> NewFeatureResult:
       return NewFeatureResult(...)
   ```

3. **第三步**：逐步重构现有代码为 dataclass

---

## 实际代码示例

### 重构前（result_service.py）

```python
def compare_runs(self, run_id_a: str, run_id_b: str) -> dict[str, Any]:
    """对比两次执行结果"""
    # ...
    return {
        "run_a": {"run_id": run_id_a, "summary": rec_a.get("summary", {})},
        "run_b": {"run_id": run_id_b, "summary": rec_b.get("summary", {})},
        "diffs": diffs,
        "total_cases": total,
        "changed_cases": len(diffs),
    }

def upload(...) -> dict[str, Any]:
    """上传结果"""
    return {
        "status": "success",
        "type": "local",
        "path": str(self.result_dir),
    }
```

### 重构后（使用 dataclass）

```python
from dataclasses import dataclass, asdict
from typing import Any

@dataclass
class RunInfo:
    """运行信息"""
    run_id: str
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class CompareResult:
    """对比结果"""
    run_a: RunInfo
    run_b: RunInfo
    diffs: list[dict[str, str]]
    total_cases: int
    changed_cases: int

    def has_changes(self) -> bool:
        """是否有变更"""
        return self.changed_cases > 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

@dataclass
class UploadResult:
    """上传结果"""
    status: str  # "success" | "error"
    type: str    # "local" | "api" | "rsync"
    message: str = ""
    path: str = ""
    response: dict[str, Any] | None = None

    @property
    def is_success(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

# 使用
def compare_runs(self, run_id_a: str, run_id_b: str) -> CompareResult:
    # ...
    return CompareResult(
        run_a=RunInfo(run_id=run_id_a, summary=rec_a.get("summary", {})),
        run_b=RunInfo(run_id=run_id_b, summary=rec_b.get("summary", {})),
        diffs=diffs,
        total_cases=total,
        changed_cases=len(diffs),
    )

def upload(...) -> UploadResult:
    return UploadResult(
        status="success",
        type="local",
        path=str(self.result_dir),
    )

# 调用方
result = service.compare_runs("run1", "run2")
print(result.changed_cases)  # ✅ IDE 自动补全
if result.has_changes():     # ✅ 可以添加业务方法
    print("有变更")
```

---

## 总结

| 场景 | 推荐方案 | 理由 |
|------|---------|------|
| 新项目 | dataclass | 类型安全、IDE友好、可扩展 |
| 现有代码最小改动 | TypedDict | 向后兼容、零侵入 |
| API 输入验证 | Pydantic | 运行时验证、自动转换 |
| 不可变数据 | NamedTuple | 轻量、线程安全 |
| 简单返回值 | TypedDict | 够用就好 |

**最佳实践**：
1. ✅ 优先使用 **dataclass**（Python 3.7+）
2. ✅ 简单场景使用 **TypedDict**
3. ✅ 需要验证时使用 **Pydantic**
4. ✅ 避免使用 `dict[str, Any]`（除非序列化中间结果）
