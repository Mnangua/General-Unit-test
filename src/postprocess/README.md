# 错误修复器 (Error Fixer)

这个模块提供了基于覆盖率的自动错误修复功能，模仿了 `CoverageBasedTestGenerator` 类的设计模式。

## 功能特性

- **自动错误检测**: 在 Docker 容器的 testbed 目录下执行覆盖率测试，捕获错误输出
- **智能错误分析**: 使用 LLM 分析错误日志，提取结构化的错误信息
- **自动代码修复**: 对每个错误，读取源文件，标注行号，使用 LLM 生成修复代码
- **迭代修复策略**: 支持多轮修复，直到所有错误解决或达到最大尝试次数
- **覆盖率跟踪**: 修复完成后重新收集覆盖率信息

## 核心类

### `CoverageBasedErrorFixer`

主要的错误修复器类，提供以下功能：

- **初始化参数**:
  - `container_name`: Docker 容器名称
  - `images`: Docker 镜像名称
  - `language`: 编程语言 (python/java)
  - `temp_dir`: 临时目录路径
  - `llm_client`: LLM 客户端实例
  - `max_fix_iterations`: 最大修复迭代次数 (默认: 3)

- **主要方法**:
  - `fix_errors_and_collect_coverage()`: 执行完整的错误修复流程

### 数据类

- **`ErrorInfo`**: 存储错误信息
  - `file_path`: 错误文件路径
  - `line_range`: 错误行范围 [start, end]
  - `message`: 错误消息

- **`FixResult`**: 存储修复结果
  - `file_path`: 修复的文件路径
  - `original_code`: 原始代码
  - `fixed_code`: 修复后的代码
  - `success`: 修复是否成功
  - `error_message`: 错误消息（如果失败）

## 使用方法

### 1. 在 run_msbench.py 中使用

```bash
python test/run_msbench.py \
    --language python \
    --enable-error-fixing \
    --max-fix-iterations 3 \
    --model claude-3.5-sonnet
```

新增的参数：
- `--enable-error-fixing`: 启用错误修复功能
- `--max-fix-iterations`: 最大修复迭代次数

### 2. 独立使用错误修复器

```python
from src.postprocess.error_fixer import create_error_fixer
from src.capi_client import CopilotProxyLLMClient

# 初始化 LLM 客户端
llm_client = CopilotProxyLLMClient(model="claude-3.5-sonnet")

# 创建错误修复器
fixer = create_error_fixer(
    container_name="my_container",
    docker_image="my_image:latest",
    language="python",
    temp_dir="./output",
    llm_client=llm_client,
    max_fix_iterations=3
)

# 执行修复
fix_results, coverage_report = fixer.fix_errors_and_collect_coverage()
```

### 3. 命令行测试

```bash
python src/postprocess/error_fixer.py \
    --container my_container \
    --language python \
    --model claude-3.5-sonnet \
    --max-iterations 3
```

或者使用测试脚本：

```bash
python test/test_error_fixer.py \
    --container my_container \
    --language python
```

## 工作流程

1. **错误检测阶段**:
   ```bash
   coverage run --source='.' \
       --omit='**/tests/**,**/test_*.py,**/*_test.py,**/__init__.py,**/.venv/**,**/.tox/**,**/.pytest_cache/**' \
       -m pytest --continue-on-collection-errors
   ```

2. **错误分析阶段**:
   - 使用 `ERROR_ANALYSIS_SYSTEM_PROMPT` 和 `ERROR_ANALYSIS_USER_PROMPT`
   - LLM 解析错误日志，提取结构化错误信息
   - 过滤重复错误和级联错误

3. **代码修复阶段**:
   - 读取包含错误的源文件
   - 为代码添加行号标注
   - 使用 `UNIT_TESTS_FIX_V1_SYSTEM_PROMPT` 和 `UNIT_TESTS_FIX_V1_USER_PROMPT`
   - LLM 生成修复后的代码
   - 将修复代码写回原文件

4. **迭代和验证**:
   - 重复上述过程，直到无错误或达到最大迭代次数
   - 最终收集覆盖率信息

## 输出结果

修改后的 `run_msbench.py` 会在 CSV 文件中添加以下新列：

- `errors_fixed`: 成功修复的错误数量
- `coverage_after_fix`: 修复后的覆盖率百分比

## 文件结构

```
src/postprocess/
├── error_fixer.py          # 主要的错误修复器实现
├── prompts.py              # LLM 提示词定义
└── openhands_editor/       # (其他相关工具)

test/
├── run_msbench.py          # 更新后的主脚本
└── test_error_fixer.py     # 错误修复器测试脚本
```

## 依赖

- `src.generate.coverage_analyzer`: 覆盖率分析
- `src.capi_client`: LLM 客户端
- `src.utils.DockerCommandRunner`: Docker 命令执行
- 标准库: `json`, `re`, `subprocess`, `pathlib`, `dataclasses`

## 注意事项

1. **LLM 客户端**: `CopilotProxyLLMClient` 使用 `query(messages)` 方法，其中 `messages` 是包含 `{"role": "system/user", "content": "..."}` 的列表
2. **文件写入**: 使用 base64 编码避免 shell 转义问题
3. **错误过滤**: 只修复根本错误，忽略级联错误
4. **安全性**: 所有文件操作都在 Docker 容器内进行
5. **容错性**: 如果 LLM 返回空修复，保持原文件不变
6. **日志记录**: 详细的进度日志和错误报告
