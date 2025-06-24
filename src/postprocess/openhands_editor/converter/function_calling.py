"""Function calling converter and interface for the standalone LLM editor."""

import json
import re
from typing import List, Dict, Any, Optional, Union


from litellm import ModelResponse, ChatCompletionToolParam


from ..core.actions import (
    Action,
    FileEditAction,
    FileReadAction,
    CmdRunAction,
    AgentFinishAction,
    MessageAction,
    FileEditSource,
    FileReadSource,
)
from ..core.exceptions import (
    FunctionCallValidationError,
    FunctionCallNotExistsError,
)
from ..tools.str_replace_editor import (
    create_str_replace_editor_tool,
    STR_REPLACE_EDITOR_TOOL_NAME,
    TOOL_EXAMPLES as STR_REPLACE_EXAMPLES,
)
from ..tools.llm_based_edit import (
    LLMBasedFileEditTool,
    LLM_BASED_EDIT_TOOL_NAME,
    TOOL_EXAMPLES as LLM_EDIT_EXAMPLES,
)


class ToolCall:
    """Tool call representation compatible with OpenAI format."""

    def __init__(self, id: str, function_name: str, arguments: Union[str, Dict[str, Any]]):
        self.id = id
        self.function = ToolCallFunction(function_name, arguments)


class ToolCallFunction:
    """Tool call function representation."""

    def __init__(self, name: str, arguments: Union[str, Dict[str, Any]]):
        self.name = name
        if isinstance(arguments, dict):
            self.arguments = json.dumps(arguments)
        else:
            self.arguments = arguments


class LLMEditorInterface:
    """Main interface for LLM-driven file editing operations."""

    def __init__(self,
                 enable_llm_based_edit: bool = True,
                 use_short_descriptions: bool = False):
        """Initialize the LLM editor interface.

        Args:
            enable_llm_based_edit: Whether to enable LLM-based editing tool
            use_short_descriptions: Whether to use short tool descriptions
        """
        self.enable_llm_based_edit = enable_llm_based_edit
        self.use_short_descriptions = use_short_descriptions

    def get_tools(self) -> List[Dict[str, Any]]:
        """Get all available tools for LLM function calling.

        Returns:
            List of tool definitions compatible with OpenAI function calling
        """
        tools = []

        # Always include str_replace_editor (OHEditor compatible)
        tools.append(create_str_replace_editor_tool(self.use_short_descriptions))

        # Optionally include LLM-based edit tool
        if self.enable_llm_based_edit:
            tools.append(LLMBasedFileEditTool)

        return tools

    def get_tool_descriptions(self) -> str:
        """Get tool descriptions in text format for non-function-calling models.

        Returns:
            Formatted tool descriptions with examples
        """
        return convert_tools_to_description(self.get_tools())

    def process_llm_response(self,
                           response: Union[Any, Dict[str, Any], str]) -> List[Action]:
        """Process LLM response and convert to actions.

        Args:
            response: LLM response in various formats

        Returns:
            List of actions to execute
        """
        if isinstance(response, str):
            # Handle text-based response (non-function-calling models)
            return self._parse_text_response(response)
        elif isinstance(response, dict):
            # Handle dictionary response
            return self._parse_dict_response(response)
        elif hasattr(response, 'choices'):
            # Handle ModelResponse object
            return response_to_actions(response)
        else:
            raise ValueError(f"Unsupported response type: {type(response)}")

    def _parse_text_response(self, text: str) -> List[Action]:
        """Parse text-based response for tool calls.

        Args:
            text: Text response from LLM

        Returns:
            List of parsed actions
        """
        actions = []

        # Look for function call patterns in text
        function_pattern = r'<function=([^>]+)>(.*?)</function>'
        matches = re.findall(function_pattern, text, re.DOTALL)

        for function_name, parameters_text in matches:
            # Parse parameters
            param_pattern = r'<parameter=([^>]+)>(.*?)</parameter>'
            param_matches = re.findall(param_pattern, parameters_text, re.DOTALL)

            arguments = {}
            for param_name, param_value in param_matches:
                arguments[param_name] = param_value.strip()

            # Create tool call object
            tool_call = ToolCall(
                id=f'text_call_{len(actions)}',
                function_name=function_name,
                arguments=arguments
            )

            # Convert to action
            action = self._tool_call_to_action(tool_call)
            if action:
                actions.append(action)

        # If no function calls found, create a message action
        if not actions:
            actions.append(MessageAction(content=text))

        return actions

    def _parse_dict_response(self, response_dict: Dict[str, Any]) -> List[Action]:
        """Parse dictionary response format.

        Args:
            response_dict: Dictionary containing response data

        Returns:
            List of parsed actions
        """
        # Handle different dictionary formats
        if 'choices' in response_dict:
            # OpenAI-style response
            choice = response_dict['choices'][0]
            message = choice.get('message', {})

            if 'tool_calls' in message:
                actions = []
                for tool_call_dict in message['tool_calls']:
                    tool_call = ToolCall(
                        id=tool_call_dict.get('id', 'dict_call'),
                        function_name=tool_call_dict['function']['name'],
                        arguments=tool_call_dict['function']['arguments']
                    )

                    action = self._tool_call_to_action(tool_call)
                    if action:
                        actions.append(action)
                return actions
            else:
                content = message.get('content', '')
                return [MessageAction(content=content)]

        # Direct tool call format
        elif 'function_name' in response_dict and 'arguments' in response_dict:
            tool_call = ToolCall(
                id='dict_call',
                function_name=response_dict['function_name'],
                arguments=response_dict['arguments']
            )

            action = self._tool_call_to_action(tool_call)
            return [action] if action else []

        return [MessageAction(content=str(response_dict))]

    def _tool_call_to_action(self, tool_call: ToolCall) -> Optional[Action]:
        """Convert a tool call to an action.

        Args:
            tool_call: Tool call object

        Returns:
            Converted action or None if conversion fails
        """
        try:
            if isinstance(tool_call.function.arguments, str):
                arguments = json.loads(tool_call.function.arguments)
            else:
                arguments = tool_call.function.arguments
        except (json.JSONDecodeError, TypeError) as e:
            raise FunctionCallValidationError(
                f'Failed to parse tool call arguments: {tool_call.function.arguments}'
            ) from e

        function_name = tool_call.function.name

        # Handle str_replace_editor tool
        if function_name == STR_REPLACE_EDITOR_TOOL_NAME:
            return self._create_str_replace_action(arguments)

        # Handle LLM-based edit tool
        elif function_name == LLM_BASED_EDIT_TOOL_NAME:
            return self._create_llm_edit_action(arguments)

        else:
            raise FunctionCallNotExistsError(
                f'Tool {function_name} is not registered. Available tools: '
                f'{[STR_REPLACE_EDITOR_TOOL_NAME, LLM_BASED_EDIT_TOOL_NAME]}'
            )

    def _create_str_replace_action(self, arguments: Dict[str, Any]) -> Action:
        """Create action from str_replace_editor tool call.

        Args:
            arguments: Tool call arguments

        Returns:
            File action (read or edit)
        """
        if 'command' not in arguments:
            raise FunctionCallValidationError('Missing required argument "command"')
        if 'path' not in arguments:
            raise FunctionCallValidationError('Missing required argument "path"')

        command = arguments['command']
        path = arguments['path']

        if command == 'view':
            return FileReadAction(
                path=path,
                impl_source=FileReadSource.OH_ACI,
                view_range=arguments.get('view_range', None),
            )
        else:
            # Filter valid arguments for FileEditAction
            valid_kwargs = {}
            valid_params = {'file_text', 'old_str', 'new_str', 'insert_line'}

            for key, value in arguments.items():
                if key in valid_params and value is not None:
                    valid_kwargs[key] = value

            return FileEditAction(
                path=path,
                command=command,
                impl_source=FileEditSource.OH_ACI,
                **valid_kwargs,
            )

    def _create_llm_edit_action(self, arguments: Dict[str, Any]) -> Action:
        """Create action from LLM-based edit tool call.

        Args:
            arguments: Tool call arguments

        Returns:
            File edit action
        """
        if 'path' not in arguments:
            raise FunctionCallValidationError('Missing required argument "path"')
        if 'content' not in arguments:
            raise FunctionCallValidationError('Missing required argument "content"')

        return FileEditAction(
            path=arguments['path'],
            content=arguments['content'],
            start=arguments.get('start', 1),
            end=arguments.get('end', -1),
            impl_source=FileEditSource.LLM_BASED_EDIT,
        )


def response_to_actions(response: Any) -> List[Action]:
    """Convert LLM response to actions (standalone version).

    Args:
        response: LLM model response

    Returns:
        List of actions to execute
    """
    actions: List[Action] = []

    if not response.choices:
        return [MessageAction(content="No response received")]

    choice = response.choices[0]
    assistant_msg = choice.message

    if hasattr(assistant_msg, 'tool_calls') and assistant_msg.tool_calls:
        # Extract thought from content if present
        thought = ''
        if isinstance(assistant_msg.content, str):
            thought = assistant_msg.content
        elif isinstance(assistant_msg.content, list):
            for msg in assistant_msg.content:
                if hasattr(msg, 'get') and msg.get('type') == 'text':
                    thought += msg.get('text', '')

        # Process each tool call
        interface = LLMEditorInterface()
        for i, tool_call in enumerate(assistant_msg.tool_calls):
            # Create our own ToolCall object from the litellm tool call
            our_tool_call = ToolCall(
                id=tool_call.id,
                function_name=tool_call.function.name,
                arguments=tool_call.function.arguments
            )

            action = interface._tool_call_to_action(our_tool_call)
            if action:
                # Add thought to first action only
                if i == 0 and thought:
                    action.thought = thought
                actions.append(action)
    else:
        # No tool calls, create message action
        content = str(assistant_msg.content) if assistant_msg.content else ''
        actions.append(MessageAction(content=content))

    return actions


def convert_tools_to_description(tools: List[Dict[str, Any]]) -> str:
    """Convert tool definitions to text descriptions for non-function-calling models.

    Args:
        tools: List of tool definitions

    Returns:
        Formatted text description of all tools
    """
    descriptions = []

    for i, tool in enumerate(tools, 1):
        if tool['type'] == 'function':
            func = tool['function']
            desc = f"---- BEGIN FUNCTION #{i}: {func['name']} ----\n"
            desc += f"Description: {func['description']}\n"

            if 'parameters' in func and 'properties' in func['parameters']:
                desc += "Parameters:\n"
                properties = func['parameters']['properties']
                required = func['parameters'].get('required', [])

                for j, (param_name, param_info) in enumerate(properties.items(), 1):
                    param_type = param_info.get('type', 'unknown')
                    param_desc = param_info.get('description', 'No description')
                    is_required = 'required' if param_name in required else 'optional'

                    desc += f"  ({j}) {param_name} ({param_type}, {is_required}): {param_desc}\n"

                    # Add enum values if present
                    if 'enum' in param_info:
                        desc += f"      Allowed values: {param_info['enum']}\n"
            else:
                desc += "No parameters are required for this function.\n"

            desc += f"---- END FUNCTION #{i} ----\n"
            descriptions.append(desc)

    # Add usage instructions
    usage_instructions = """
You have access to the following functions:

{descriptions}

If you choose to call a function ONLY reply in the following format with NO suffix:

<function=example_function_name>
<parameter=example_parameter_1>value_1</parameter>
<parameter=example_parameter_2>
This is the value for the second parameter
that can span
multiple lines
</parameter>
</function>

<IMPORTANT>
Reminder:
- Function calls MUST follow the specified format, start with <function= and end with </function>
- Required parameters MUST be specified
- Only call one function at a time
- You may provide optional reasoning for your function call in natural language BEFORE the function call, but NOT after.
- If there is no function call available, answer the question like normal with your current knowledge and do not tell the user about function calls
</IMPORTANT>
"""

    return usage_instructions.format(descriptions='\n'.join(descriptions))


def convert_fncall_to_non_fncall_format(tool_calls: List[Dict[str, Any]]) -> str:
    """Convert function calls to text format for non-function-calling models.

    Args:
        tool_calls: List of function call dictionaries

    Returns:
        Formatted text representation of function calls
    """
    if not tool_calls:
        return ""

    result = []

    for tool_call in tool_calls:
        if 'function' not in tool_call:
            continue

        function_name = tool_call['function']['name']
        try:
            if isinstance(tool_call['function']['arguments'], str):
                arguments = json.loads(tool_call['function']['arguments'])
            else:
                arguments = tool_call['function']['arguments']
        except (json.JSONDecodeError, TypeError):
            continue

        call_text = f"<function={function_name}>\n"

        for param_name, param_value in arguments.items():
            call_text += f"<parameter={param_name}>\n{param_value}\n</parameter>\n"

        call_text += "</function>"
        result.append(call_text)

    return '\n'.join(result)


def get_tool_examples() -> Dict[str, Dict[str, str]]:
    """Get tool usage examples for in-context learning.

    Returns:
        Dictionary of tool examples organized by tool and scenario
    """
    return {
        'str_replace_editor': STR_REPLACE_EXAMPLES,
        'edit_file': LLM_EDIT_EXAMPLES,
    }


def create_tool_call_from_dict(tool_call_dict: Dict[str, Any]) -> ToolCall:
    """Create a ToolCall object from a dictionary representation.

    Args:
        tool_call_dict: Dictionary containing tool call data

    Returns:
        ToolCall object
    """
    return ToolCall(
        id=tool_call_dict.get('id', 'unknown'),
        function_name=tool_call_dict['function']['name'],
        arguments=tool_call_dict['function']['arguments']
    )


def create_tool_call_from_text(function_name: str, arguments: Dict[str, Any], call_id: str = None) -> ToolCall:
    """Create a ToolCall object from function name and arguments.

    Args:
        function_name: Name of the function to call
        arguments: Arguments for the function
        call_id: Optional call ID

    Returns:
        ToolCall object
    """
    if call_id is None:
        call_id = f"call_{hash(function_name + str(arguments)) % 10000}"

    return ToolCall(
        id=call_id,
        function_name=function_name,
        arguments=arguments
    )
