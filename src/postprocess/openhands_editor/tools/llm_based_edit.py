"""LLM-based file editing tool definition."""

from typing import Dict, Any

# Tool name constant
LLM_BASED_EDIT_TOOL_NAME = 'edit_file'

from litellm import ChatCompletionToolParam, ChatCompletionToolParamFunctionChunk


_FILE_EDIT_DESCRIPTION = """Edit a file in plain-text format.
* The assistant can edit files by specifying the file path and providing a draft of the new file content.
* The draft content doesn't need to be exactly the same as the existing file; the assistant may skip unchanged lines using comments like `# ... existing code ...` to indicate unchanged sections.
* IMPORTANT: For large files (e.g., > 300 lines), specify the range of lines to edit using `start` and `end` (1-indexed, inclusive). The range should be smaller than 300 lines.
* -1 indicates the last line of the file when used as the `start` or `end` value.
* Keep at least one unchanged line before the changed section and after the changed section wherever possible.
* Make sure to set the `start` and `end` to include all the lines in the original file referred to in the draft of the new file content. Failure to do so will result in bad edits.
* To append to a file, set both `start` and `end` to `-1`.
* If the file doesn't exist, a new file will be created with the provided content.
* IMPORTANT: Make sure you include all the required indentations for each line of code in the draft, otherwise the edited code will be incorrectly indented.
* IMPORTANT: Make sure that the first line of the draft is also properly indented and has the required whitespaces.
* IMPORTANT: NEVER include or make references to lines from outside the `start` and `end` range in the draft.
* IMPORTANT: Start the content with a comment in the format: #EDIT: Reason for edit
* IMPORTANT: If you are not appending to the file, avoid setting `start` and `end` to the same value.

**Example 1: general edit for short files**
For example, given an existing file `/path/to/file.py` that looks like this:
(this is the beginning of the file)
1|class MyClass:
2|    def __init__(self):
3|        self.x = 1
4|        self.y = 2
5|        self.z = 3
6|
7|print(MyClass().z)
8|print(MyClass().x)
(this is the end of the file)

The assistant wants to edit the file to look like this:
(this is the beginning of the file)
1|class MyClass:
2|    def __init__(self):
3|        self.x = 1
4|        self.y = 2
5|
6|print(MyClass().y)
(this is the end of the file)

The assistant may produce an edit action like this:
path="/path/to/file.txt" start=1 end=-1
content=```
#EDIT: I want to change the value of y to 2
class MyClass:
    def __init__(self):
        # ... existing code ...
        self.y = 2

print(MyClass().y)
```

**Example 2: append to file for short files**
For example, given an existing file `/path/to/file.py` that looks like this:
(this is the beginning of the file)
1|class MyClass:
2|    def __init__(self):
3|        self.x = 1
4|        self.y = 2
5|        self.z = 3
6|
7|print(MyClass().z)
8|print(MyClass().x)
(this is the end of the file)

To append the following lines to the file:
```python
#EDIT: I want to print the value of y
print(MyClass().y)
```

The assistant may produce an edit action like this:
path="/path/to/file.txt" start=-1 end=-1
content=```
print(MyClass().y)
```

**Example 3: edit for long files**

Given an existing file `/path/to/file.py` that looks like this:
(1000 more lines above)
1001|class MyClass:
1002|    def __init__(self):
1003|        self.x = 1
1004|        self.y = 2
1005|        self.z = 3
1006|
1007|print(MyClass().z)
1008|print(MyClass().x)
(2000 more lines below)

The assistant wants to edit the file to look like this:

(1000 more lines above)
1001|class MyClass:
1002|    def __init__(self):
1003|        self.x = 1
1004|        self.y = 2
1005|
1006|print(MyClass().y)
(2000 more lines below)

The assistant may produce an edit action like this:
path="/path/to/file.txt" start=1002 end=1008
content=```
#EDIT: I want to change the value of y to 2
    def __init__(self):
        # no changes before
        self.y = 2
        # self.z is removed

# MyClass().z is removed
print(MyClass().y)
```
"""


LLMBasedFileEditTool: Dict[str, Any] = {
    'type': 'function',
    'function': {
        'name': LLM_BASED_EDIT_TOOL_NAME,
        'description': _FILE_EDIT_DESCRIPTION,
        'parameters': {
            'type': 'object',
            'properties': {
                'path': {
                    'type': 'string',
                    'description': 'The absolute path to the file to be edited.',
                },
                'content': {
                    'type': 'string',
                    'description': 'A draft of the new content for the file being edited. Note that the assistant may skip unchanged lines.',
                },
                'start': {
                    'type': 'integer',
                    'description': 'The starting line number for the edit (1-indexed, inclusive). Default is 1.',
                },
                'end': {
                    'type': 'integer',
                    'description': 'The ending line number for the edit (1-indexed, inclusive). Default is -1 (end of file).',
                },
            },
            'required': ['path', 'content'],
        },
    },
}


# Tool examples for in-context learning
TOOL_EXAMPLES = {
    'create_file': """
ASSISTANT: There is no `app.py` file in the current directory. Let me create a Python file `app.py`:
<function=edit_file>
<parameter=path>/workspace/app.py</parameter>
<parameter=start>1</parameter>
<parameter=end>-1</parameter>
<parameter=content>
from flask import Flask
app = Flask(__name__)

@app.route('/')
def index():
    numbers = list(range(1, 11))
    return str(numbers)

if __name__ == '__main__':
    app.run(port=5000)
</parameter>
</function>

USER: EXECUTION RESULT of [edit_file]:
File created successfully at: /workspace/app.py
""",
    'edit_file': """
ASSISTANT: Now let me display the numbers in a table format:
<function=edit_file>
<parameter=path>/workspace/app.py</parameter>
<parameter=start>6</parameter>
<parameter=end>9</parameter>
<parameter=content>
    numbers = list(range(1, 11))
    return '<table>' + ''.join([f'<tr><td>{i}</td></tr>' for i in numbers]) + '</table>'
    # ... existing code ...
if __name__ == '__main__':
</parameter>
</function>

USER: EXECUTION RESULT of [edit_file]:
The file /workspace/app.py has been edited. Here's the result of running `cat -n` on a snippet of /workspace/app.py:
     3
     4  @app.route('/')
     5  def index():
     6      numbers = list(range(1, 11))
     7      return '<table>' + ''.join([f'<tr><td>{i}</td></tr>' for i in numbers]) + '</table>'
     8
     9  if __name__ == '__main__':
    10      app.run(port=5000)
Review the changes and make sure they are as expected. Edit the file again if necessary.
""",
}
