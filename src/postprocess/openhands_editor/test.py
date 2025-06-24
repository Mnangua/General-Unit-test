# prompts.py
"""
LLM Code Fix Prompt Template for OpenHands OHEditor Integration
完整的代码修复提示模板，用于生成可被 OpenHands 处理的编辑命令
"""

from src.deepprompt_client import query

class CodeFixPromptTemplate:
    """代码修复提示模板类"""

    SYSTEM_PROMPT = """You are an expert code fixing assistant that generates precise file edits for OpenHands.

Your task is to analyze code errors and generate edit commands that can be processed by the str_replace_editor tool in OpenHands.

CRITICAL REQUIREMENTS:

1. **Output Format**: You MUST respond with ONE of these two formats:

   Format A - str_replace_editor tool call (for OHEditor):
   ```
   <function=str_replace_editor>
   <parameter=command>str_replace</parameter>
   <parameter=path>{file_path}</parameter>
   <parameter=old_str>{exact_problematic_code}</parameter>
   <parameter=new_str>{fixed_code}</parameter>
   </function>
   ```

   Format B - edit_file tool call (for LLM-based editing):
   ```
   <function=edit_file>
   <parameter=path>{file_path}</parameter>
   <parameter=start>{start_line}</parameter>
   <parameter=end>{end_line}</parameter>
   <parameter=content>
   #EDIT: Fix {error_description}
   {fixed_code_with_proper_indentation}
   </parameter>
   </function>
   ```

2. **Exact Matching (Format A)**: The `old_str` must match EXACTLY the problematic code including:
   - All whitespace and indentation
   - Line breaks
   - Comments
   - Include sufficient context (2-3 lines before/after) to ensure uniqueness

3. **Proper Indentation (Format B)**: Ensure all lines have correct indentation matching the file structure.

4. **Error Analysis**: Always understand the root cause before fixing.

5. **Minimal Changes**: Make only necessary changes to fix the specific error.

CHOOSE FORMAT BASED ON:
- Use Format A (str_replace_editor) when the error is localized and you can precisely identify the exact text to replace
- Use Format B (edit_file) when the fix requires understanding broader context or multiple line changes

NEVER:
- Output explanations after the function call
- Make unnecessary changes beyond fixing the error
- Include line numbers in the old_str (Format A)
- Reference lines outside the specified range (Format B)"""

    USER_PROMPT_TEMPLATE = """Please fix the following code error:

**File**: {file_path}
**Error Lines**: {error_start_line}-{error_end_line}
**Error Message**: {error_message}

**Current Code Context**:
```{file_extension}
{code_context}
```

**Specific Problematic Section** (lines {error_start_line}-{error_end_line}):
```{file_extension}
{problematic_code}
```

**Additional Context** (if provided):
{additional_context}

Generate the appropriate edit command to fix this error."""

    @classmethod
    def create_prompts(
        cls,
        file_path: str,
        error_start_line: int,
        error_end_line: int,
        error_message: str,
        code_context: str,
        problematic_code: str,
        additional_context: str = "",
        file_extension: str = "python"
    ) -> tuple[str, str]:
        """
        创建系统和用户提示

        Args:
            file_path: 错误文件路径
            error_start_line: 错误开始行号
            error_end_line: 错误结束行号
            error_message: 具体错误信息
            code_context: 错误周围的代码上下文
            problematic_code: 具体的问题代码段
            additional_context: 额外的上下文信息
            file_extension: 文件扩展名，用于语法高亮

        Returns:
            元组 (system_prompt, user_prompt)
        """
        user_prompt = cls.USER_PROMPT_TEMPLATE.format(
            file_path=file_path,
            error_start_line=error_start_line,
            error_end_line=error_end_line,
            error_message=error_message,
            code_context=code_context,
            problematic_code=problematic_code,
            additional_context=additional_context if additional_context else "None",
            file_extension=file_extension
        )

        return cls.SYSTEM_PROMPT, user_prompt


class CodeContextExtractor:
    """代码上下文提取器"""

    @staticmethod
    def extract_context(
        file_content: str,
        error_start_line: int,
        error_end_line: int = None,
        context_lines: int = 5
    ) -> tuple[str, str]:
        """
        从文件内容中提取错误上下文

        Args:
            file_content: 完整文件内容
            error_start_line: 错误开始行号 (1-indexed)
            error_end_line: 错误结束行号 (1-indexed)，如果为 None 则等于 error_start_line
            context_lines: 上下文行数

        Returns:
            元组 (code_context, problematic_code)
        """
        if error_end_line is None:
            error_end_line = error_start_line

        lines = file_content.split('\n')
        total_lines = len(lines)

        # 计算上下文范围
        start_idx = max(0, error_start_line - 1 - context_lines)
        end_idx = min(total_lines, error_end_line + context_lines)

        # 提取上下文并添加行号
        context_lines_list = []
        for i in range(start_idx, end_idx):
            line_num = i + 1
            line_content = lines[i] if i < len(lines) else ""
            # 标记错误行
            if error_start_line <= line_num <= error_end_line:
                context_lines_list.append(f"{line_num:3d}|{line_content}  # <-- ERROR LINE")
            else:
                context_lines_list.append(f"{line_num:3d}|{line_content}")

        code_context = '\n'.join(context_lines_list)

        # 提取问题代码段
        problematic_lines = []
        for line_num in range(error_start_line, error_end_line + 1):
            if line_num <= len(lines):
                problematic_lines.append(lines[line_num - 1])

        problematic_code = '\n'.join(problematic_lines)

        return code_context, problematic_code


class LLMCodeFixer:
    """LLM 代码修复器"""

    def __init__(self):
        """
        初始化代码修复器

        Args:
            llm: OpenHands LLM 实例
        """
        self.prompt_template = CodeFixPromptTemplate()
        self.context_extractor = CodeContextExtractor()

    def generate_fix(
        self,
        file_path: str,
        file_content: str,
        error_start_line: int,
        error_message: str,
        error_end_line: int = None,
        additional_context: str = "",
        context_lines: int = 5
    ) -> str:
        """
        使用 LLM 生成代码修复命令

        Args:
            file_path: 文件路径
            file_content: 文件内容
            error_start_line: 错误开始行号
            error_message: 错误消息
            error_end_line: 错误结束行号，默认为 None
            additional_context: 额外上下文
            context_lines: 上下文行数

        Returns:
            LLM 生成的修复命令字符串
        """
        # 确定错误结束行
        if error_end_line is None:
            error_end_line = error_start_line

        # 提取代码上下文
        code_context, problematic_code = self.context_extractor.extract_context(
            file_content=file_content,
            error_start_line=error_start_line,
            error_end_line=error_end_line,
            context_lines=context_lines
        )

        # 确定文件扩展名
        file_extension = self._get_file_extension(file_path)

        # 生成提示
        system_prompt, user_prompt = self.prompt_template.create_prompts(
            file_path=file_path,
            error_start_line=error_start_line,
            error_end_line=error_end_line,
            error_message=error_message,
            code_context=code_context,
            problematic_code=problematic_code,
            additional_context=additional_context,
            file_extension=file_extension
        )

        # 调用 LLM
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        response = query(messages=messages)
        return response

    @staticmethod
    def _get_file_extension(file_path: str) -> str:
        """获取文件扩展名"""
        if '.' in file_path:
            return file_path.split('.')[-1]
        return "text"


def example_multi_line_error():
    """多行错误示例"""
    file_path = "/home/mengnanqi/General-Unit-Test/openhands_workspace/calculator.py"
    file_content = open(file_path, 'r').read()

    error_start_line = 20
    error_end_line = 23
    error_message = "Unhandled exception: ValueError may be raised by divide() but not caught"
    additional_context = "Add proper exception handling for division by zero in calculate_average method."

    # 提取上下文
    code_context, problematic_code = CodeContextExtractor.extract_context(
        file_content, error_start_line, error_end_line
    )

    # 创建提示
    system_prompt, user_prompt = CodeFixPromptTemplate.create_prompts(
        file_path=file_path,
        error_start_line=error_start_line,
        error_end_line=error_end_line,
        error_message=error_message,
        code_context=code_context,
        problematic_code=problematic_code,
        additional_context=additional_context,
        file_extension="python"
    )

    print("\n=== 多行错误示例 ===")
    print("USER PROMPT:")
    print(user_prompt)
    print("\n期望的 LLM 响应:")
    print("""<function=edit_file>
<parameter=path>/workspace/calculator.py</parameter>
<parameter=start>18</parameter>
<parameter=end>23</parameter>
<parameter=content>
#EDIT: Add proper exception handling for division by zero
    def calculate_average(self, numbers):
        if not numbers:
            return 0
        total = sum(numbers)
        count = len(numbers)
        try:
            average = self.divide(total, count)
            return average
        except ValueError as e:
            print(f"Error calculating average: {e}")
            return 0
</parameter>
</function>""")
    
    fixer = LLMCodeFixer()
    fix_command = fixer.generate_fix(
        file_path=file_path,
        file_content=file_content,
        error_start_line=error_start_line,
        error_end_line=error_end_line,
        error_message=error_message,
        additional_context=additional_context
    )

    print("生成的修复命令:")
    print(fix_command)


if __name__ == "__main__":
    example_multi_line_error()
