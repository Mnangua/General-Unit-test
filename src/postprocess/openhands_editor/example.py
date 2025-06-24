# 文件: standalone_llm_editor/examples/basic_usage.py
"""Basic usage example for the standalone LLM editor."""

import json
from typing import Dict, Any

from openhands_aci.editor.editor import OHEditor
from src.postprocess.openhands_editor import (
    LLMEditorInterface,
    FileEditAction,
    FileReadAction,
    FileEditSource,
)


def demonstrate_basic_usage():
    """Demonstrate basic usage of the LLM editor interface."""
    print("🚀 Standalone LLM Editor - Basic Usage Demo")
    print("=" * 50)
    
    # 1. Initialize the editor interface
    editor_interface = LLMEditorInterface(
        enable_llm_based_edit=True,
        use_short_descriptions=False
    )
    
    # 2. Get tools for LLM
    tools = editor_interface.get_tools()
    print(f"📋 Available tools: {len(tools)}")
    for tool in tools:
        print(f"  - {tool['function']['name']}")
    
    # 3. Get tool descriptions for non-function-calling models
    print("\n📝 Tool descriptions for text-based models:")
    descriptions = editor_interface.get_tool_descriptions()
    print(descriptions[:500] + "..." if len(descriptions) > 500 else descriptions)
    
    # 4. Simulate LLM responses and convert to actions
    print("\n🤖 Processing LLM responses:")
        
    # Example 3: Text-based response (non-function-calling model)
    text_response = '''
<function=edit_file>
<parameter=path>/home/mengnanqi/General-Unit-Test/openhands_workspace/calculator.py</parameter>
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
</function>
'''
    
    actions = editor_interface.process_llm_response(text_response)
    print(f"\n💬 Text response action: {actions}")

    edit_action = actions[0]

    editor = OHEditor(workspace_root="/home/mengnanqi/General-Unit-Test/openhands_workspace")

    result = editor(
        command=edit_action.command,
        path=edit_action.path,
        old_str=edit_action.old_str,
        new_str=edit_action.new_str
    )
    print(f"✅ Result: {result.output}")


def demonstrate_file_operations():
    """Demonstrate file operations with mock editor."""
    print("\n🔧 File Operations Demo")
    print("=" * 30)
    
    editor = OHEditor(workspace_root="/tmp/demo")
    
    # Create file action
    create_action = FileEditAction(
        path="/workspace/demo.py",
        command="create",
        file_text="def hello():\n    print('Hello from LLM Editor!')\n",
        impl_source=FileEditSource.OH_ACI
    )
    
    print(f"📝 Executing: {create_action}")
    
    try:
        result = editor(
            command=create_action.command,
            path=create_action.path,
            file_text=create_action.file_text
        )
        print(f"✅ Result: {result.output}")
        
        # Edit file action
        edit_action = FileEditAction(
            path="/workspace/demo.py",
            command="str_replace",
            old_str="Hello from LLM Editor!",
            new_str="Hello from Standalone LLM Editor!",
            impl_source=FileEditSource.OH_ACI
        )
        
        print(f"\n✏️ Executing: {edit_action}")
        
        result = editor(
            command=edit_action.command,
            path=edit_action.path,
            old_str=edit_action.old_str,
            new_str=edit_action.new_str
        )
        print(f"✅ Result: {result.output}")
        
        # View file action
        view_action = FileReadAction(
            path="/workspace/demo.py",
            impl_source=FileEditSource.OH_ACI
        )
        
        print(f"\n👀 Executing: {view_action}")
        
        result = editor(
            command="view",
            path=view_action.path
        )
        print(f"✅ Result: {result.output}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    demonstrate_basic_usage()
    #demonstrate_file_operations()
