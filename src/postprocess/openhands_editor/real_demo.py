#!/usr/bin/env python3
"""
真实的 LLM 编辑器使用示例 - 无 Mock 操作
演示如何将这个独立模块集成到实际项目中
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, Any, List

# 导入我们的独立模块
from src.postprocess.openhands_editor import (
    LLMEditorInterface,
    FileEditAction,
    FileReadAction,
    FileEditSource,
)

from openhands_aci.editor.editor import OHEditor


class RealLLMEditorDemo:
    """真实的 LLM 编辑器演示类"""

    def __init__(self, workspace_root: str):

        self.workspace_root = workspace_root
        # 初始化编辑器接口
        self.editor_interface = LLMEditorInterface(
            enable_llm_based_edit=True,
            use_short_descriptions=False
        )

        self.file_editor = OHEditor(workspace_root=self.workspace_root)

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取工具定义"""
        return self.editor_interface.get_tools()

    def get_text_tool_descriptions(self) -> str:
        """获取文本格式的工具描述"""
        return self.editor_interface.get_tool_descriptions()

    def process_llm_function_call(self, function_name: str, arguments: Dict[str, Any]) -> List[Any]:
        """处理 LLM 的函数调用"""
        import json
        
        # 模拟 LLM 响应格式
        llm_response = {
            'choices': [{
                'message': {
                    'content': f"I'll use the {function_name} tool.",
                    'tool_calls': [{
                        'id': 'call_1',
                        'function': {
                            'name': function_name,
                            'arguments': json.dumps(arguments) if isinstance(arguments, dict) else arguments
                        }
                    }]
                }
            }]
        }

        # 转换为 actions
        actions = self.editor_interface.process_llm_response(llm_response)
        return actions

    def process_text_based_llm_response(self, text_response: str) -> List[Any]:
        """处理文本格式的 LLM 响应"""
        actions = self.editor_interface.process_llm_response(text_response)
        return actions

    def execute_file_action(self, action) -> Dict[str, Any]:
        """执行文件操作 action"""
        if not self.file_editor:
            return {
                "success": False,
                "error": "OHEditor not available. Please install openhands-aci.",
                "output": None
            }

        try:
            if isinstance(action, FileEditAction):
                # 检查是 OH_ACI 还是 LLM_BASED_EDIT
                if action.impl_source == FileEditSource.LLM_BASED_EDIT:
                    # LLM-based 编辑：需要特殊处理
                    return self._handle_llm_based_edit(action)
                else:
                    # OH_ACI 编辑：直接传递给 OHEditor
                    result = self.file_editor(
                        command=action.command,
                        path=action.path,
                        file_text=action.file_text,
                        old_str=action.old_str,
                        new_str=action.new_str,
                        insert_line=action.insert_line,
                        enable_linting=False
                    )

                    return {
                        "success": not result.error,
                        "error": result.error,
                        "output": result.output,
                        "old_content": result.old_content,
                        "new_content": result.new_content
                    }

            elif isinstance(action, FileReadAction):
                # 执行文件读取
                result = self.file_editor(
                    command="view",
                    path=action.path,
                    view_range=action.view_range,
                    enable_linting=False
                )

                return {
                    "success": not result.error,
                    "error": result.error,
                    "output": result.output
                }

            else:
                return {
                    "success": False,
                    "error": f"Unsupported action type: {type(action)}",
                    "output": None
                }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "output": None
            }

    def _handle_llm_based_edit(self, action: FileEditAction) -> Dict[str, Any]:
        """处理 LLM-based 编辑操作"""
        try:
            # 先读取文件内容（如果文件存在）
            try:
                view_result = self.file_editor(
                    command="view",
                    path=action.path,
                    enable_linting=False
                )
                if view_result.error:
                    # 文件不存在，创建新文件
                    old_content = ""
                    file_lines = []
                else:
                    old_content = view_result.output
                    # 移除行号前缀（OHEditor view 会添加行号）
                    file_lines = []
                    for line in old_content.split('\n'):
                        if '|' in line and line.strip():
                            # 格式类似 "  1|content"，提取内容部分
                            parts = line.split('|', 1)
                            if len(parts) == 2:
                                file_lines.append(parts[1])
                            else:
                                file_lines.append(line)
                        else:
                            file_lines.append(line)
            except Exception:
                old_content = ""
                file_lines = []

            # 处理 start 和 end 参数
            start = int(action.start) if isinstance(action.start, str) else action.start
            end = int(action.end) if isinstance(action.end, str) else action.end

            # 处理负数索引
            if start == -1:
                start = len(file_lines) + 1
            if end == -1:
                end = len(file_lines)

            # 构建新的文件内容
            new_lines = []

            # 添加开始之前的行
            if start > 1:
                new_lines.extend(file_lines[:start-1])

            # 添加新内容（移除 #EDIT: 注释）
            content_lines = action.content.strip().split('\n')
            if content_lines and content_lines[0].strip().startswith('#EDIT:'):
                content_lines = content_lines[1:]  # 移除第一行的 #EDIT: 注释

            new_lines.extend(content_lines)

            # 添加结束之后的行
            if end < len(file_lines):
                new_lines.extend(file_lines[end:])

            # 创建或覆盖文件
            new_content = '\n'.join(new_lines)

            # 使用 OHEditor 的 create 命令写入文件
            result = self.file_editor(
                command="create" if not old_content else "str_replace",
                path=action.path,
                file_text=new_content if not old_content else None,
                old_str=old_content if old_content else None,
                new_str=new_content if old_content else None,
                enable_linting=False
            )

            return {
                "success": not result.error,
                "error": result.error,
                "output": result.output,
                "old_content": old_content,
                "new_content": new_content
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"LLM-based edit failed: {str(e)}",
                "output": None
            }

    def demo_function_calling_workflow(self):
        """演示函数调用工作流"""
        print("\n🎯 演示函数调用工作流")
        print("=" * 50)

        # 1. 获取工具定义
        tools = self.get_tool_definitions()
        print(f"📋 可用工具数量: {len(tools)}")
        for tool in tools:
            print(f"  - {tool['function']['name']}")

        # 2. 模拟创建文件的 LLM 函数调用
        print("\n📝 步骤 1: 创建 Python 文件")
        create_args = {
            'command': 'create',
            'path': f'{self.workspace_root}/examples.py',
            'file_text': '''def greet(name):
    """简单的问候函数"""
    return f"Hello, {name}!"

def main():
    print(greet("World"))

if __name__ == "__main__":
    main()
'''
        }

        actions = self.process_llm_function_call('str_replace_editor', create_args)
        print(f"生成的 actions: {len(actions)}")

        for action in actions:
            result = self.execute_file_action(action)
            if result["success"]:
                print(f"✅ 文件创建成功: {result['output']}")
            else:
                print(f"❌ 文件创建失败: {result['error']}")

        # 3. 模拟编辑文件的 LLM 函数调用
        print("\n✏️ 步骤 2: 编辑文件内容")
        edit_args = {
            'command': 'str_replace',
            'path': f'{self.workspace_root}/examples.py',
            'old_str': '    return f"Hello, {name}!"',
            'new_str': '    return f"Hello, {name}! Welcome to the LLM Editor!"'
        }

        actions = self.process_llm_function_call('str_replace_editor', edit_args)

        for action in actions:
            result = self.execute_file_action(action)
            if result["success"]:
                print(f"✅ 文件编辑成功: {result['output']}")
            else:
                print(f"❌ 文件编辑失败: {result['error']}")

        # 4. 查看最终文件内容
        print("\n👀 步骤 3: 查看文件内容")
        view_args = {
            'command': 'view',
            'path': f'{self.workspace_root}/examples.py'
        }

        actions = self.process_llm_function_call('str_replace_editor', view_args)

        for action in actions:
            result = self.execute_file_action(action)
            if result["success"]:
                print(f"📄 文件内容:\n{result['output']}")
            else:
                print(f"❌ 文件查看失败: {result['error']}")

    def demo_text_based_workflow(self):
        """演示文本格式工作流"""
        print("\n🎯 演示文本格式工作流")
        print("=" * 50)

        # 1. 获取文本格式工具描述
        tool_descriptions = self.get_text_tool_descriptions()
        print(f"📖 工具描述长度: {len(tool_descriptions)} 字符")
        print("📖 工具描述片段:")
        print(tool_descriptions[:300] + "...")

        # 2. 模拟文本格式的 LLM 响应
        text_response = f'''Let me create a configuration file for the project.

<function=str_replace_editor>
<parameter=command>create</parameter>
<parameter=path>{self.workspace_root}/config.json</parameter>
<parameter=file_text>{{
    "project_name": "LLM Editor Demo",
    "version": "1.0.0",
    "author": "AI Assistant",
    "settings": {{
        "auto_save": true,
        "theme": "dark",
        "language": "python"
    }}
}}
</parameter>
</function>'''

        print(f"\n💬 处理文本格式 LLM 响应")
        actions = self.process_text_based_llm_response(text_response)
        print(f"解析出的 actions: {len(actions)}")

        for action in actions:
            result = self.execute_file_action(action)
            if result["success"]:
                print(f"✅ 操作成功: {result['output']}")
            else:
                print(f"❌ 操作失败: {result['error']}")


def main():
    # 创建演示实例
    demo = RealLLMEditorDemo("/home/mengnanqi/General-Unit-Test/openhands_workspace")

    # 运行各种演示
    #demo.demo_function_calling_workflow()
    demo.demo_text_based_workflow()


if __name__ == "__main__":
    main()
