import os
import sys
import ast
import re
from typing import List, Dict, Tuple, Optional, Set, Union
from dataclasses import dataclass
from enum import Enum

import tree_sitter_python
from tree_sitter import Language, Parser

class CallableType(Enum):
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    ASYNC_METHOD = "async_method"
    STATIC_METHOD = "static_method"
    CLASS_METHOD = "class_method"
    PROPERTY = "property"
    LAMBDA = "lambda"
    GLOBAL_VARIABLE = "global_variable"
    CLASS_VARIABLE = "class_variable"
    CONSTANT = "constant"
    DECORATED_FUNCTION = "decorated_function"
    DECORATED_CLASS = "decorated_class"
    MAGIC_METHOD = "magic_method"
    PRIVATE_METHOD = "private_method"
    PROTECTED_METHOD = "protected_method"

@dataclass
class CallableElement:
    """Represents a callable Python code element"""
    name: str
    callable_type: CallableType
    code: str
    signature: str
    decorators: List[str]
    line_start: int
    line_end: int
    module_path: Optional[str] = None
    class_name: Optional[str] = None
    docstring: Optional[str] = None
    parameters: List[str] = None
    return_annotation: Optional[str] = None
    is_public: bool = True
    is_exported: bool = True

class PythonCallableExtractor:
    """Python code callable element extractor"""
    
    def __init__(self):
        self.language = Language(tree_sitter_python.language())
        self.parser = Parser(self.language)
        self.code = ""
        self.code_bytes = b""
        self.code_lines = []
        
    def extract_all_callable_elements(self, python_code: str) -> List[CallableElement]:
        """
        Extract all elements that can be called by other code from Python code
        
        Args:
            python_code: Complete Python source code string
            
        Returns:
            List containing all callable elements
        """
        self.code = python_code
        self.code_bytes = python_code.encode('utf-8')
        self.code_lines = python_code.split('\n')
        tree = self.parser.parse(self.code_bytes)
        root_node = tree.root_node
        
        callable_elements = []
        
        # Extract module-level callable elements
        callable_elements.extend(self._extract_module_level_elements(root_node))
        
        # Extract classes and their members
        callable_elements.extend(self._extract_classes_and_members(root_node))
        
        # Extract global variables and constants
        callable_elements.extend(self._extract_global_variables(root_node))
        
        return callable_elements
    
    def _extract_module_level_elements(self, root_node) -> List[CallableElement]:
        """Extract module-level functions and classes"""
        elements = []
        
        # Find module-level function definitions
        for child in root_node.children:
            if child.type in ["function_definition", "async_function_definition"]:
                element = self._extract_function(child, None)
                if element:
                    elements.append(element)
            elif child.type == "class_definition":
                element = self._extract_class(child)
                if element:
                    elements.append(element)
            elif child.type == "decorated_definition":
                element = self._extract_decorated_definition(child, None)
                if element:
                    elements.append(element)
                    
        return elements
    
    def _extract_classes_and_members(self, root_node) -> List[CallableElement]:
        """Extract classes and their member methods"""
        elements = []
        
        class_nodes = self._find_nodes_by_type(root_node, "class_definition")
        
        for class_node in class_nodes:
            class_name = self._get_class_name(class_node)
            
            # Extract methods in class
            method_nodes = self._find_direct_children_by_type(class_node, [
                "function_definition", 
                "async_function_definition",
                "decorated_definition"
            ])
            
            for method_node in method_nodes:
                if method_node.type == "decorated_definition":
                    element = self._extract_decorated_definition(method_node, class_name)
                else:
                    element = self._extract_function(method_node, class_name)
                if element:
                    elements.append(element)
                    
        return elements
    
    def _extract_class(self, node) -> Optional[CallableElement]:
        """Extract class definition"""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
            
        name = self._get_node_text(name_node)
        code = self._get_node_text(node)
        
        # Get decorators
        decorators = self._get_decorators_for_node(node)
        
        # Get docstring
        docstring = self._extract_docstring(node)
        
        # Get base classes
        bases = self._get_base_classes(node)
        
        # Build signature
        base_str = f"({', '.join(bases)})" if bases else ""
        decorator_str = '\n'.join([f"@{dec}" for dec in decorators])
        signature = f"{decorator_str}\nclass {name}{base_str}:".strip()
        
        # Determine if it's a public class
        is_public = not name.startswith('_')
        
        callable_type = CallableType.DECORATED_CLASS if decorators else CallableType.CLASS
        
        return CallableElement(
            name=name,
            callable_type=callable_type,
            code=code,
            signature=signature,
            decorators=decorators,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            class_name=name,
            docstring=docstring,
            is_public=is_public
        )
    
    def _extract_function(self, node, class_name: Optional[str]) -> Optional[CallableElement]:
        """Extract function or method definition"""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
            
        name = self._get_node_text(name_node)
        code = self._get_node_text(node)
        
        # Get decorators
        decorators = self._get_decorators_for_node(node)
        
        # Get docstring
        docstring = self._extract_docstring(node)
        
        # Get parameters
        parameters = self._extract_parameters(node)
        
        # Get return type annotation
        return_annotation = self._extract_return_annotation(node)
        
        # Determine function type
        callable_type = self._determine_function_type(node, name, decorators, class_name)
        
        # Build signature
        signature = self._build_function_signature(node, name, parameters, return_annotation, decorators)
        
        # Determine visibility
        is_public = self._is_public_function(name, class_name)
        
        return CallableElement(
            name=name,
            callable_type=callable_type,
            code=code,
            signature=signature,
            decorators=decorators,
            line_start=node.start_point[0] + 1,
            line_end=node.end_point[0] + 1,
            class_name=class_name,
            docstring=docstring,
            parameters=parameters,
            return_annotation=return_annotation,
            is_public=is_public
        )
    
    def _extract_decorated_definition(self, node, class_name: Optional[str]) -> Optional[CallableElement]:
        """Extract decorator definition"""
        # Find decorator nodes
        decorators = []
        target_node = None
        
        for child in node.children:
            if child.type == "decorator":
                decorator_text = self._get_node_text(child)[1:]  # Remove @ symbol
                decorators.append(decorator_text)
            elif child.type in ["function_definition", "async_function_definition", "class_definition"]:
                target_node = child
                
        if not target_node:
            return None
            
        if target_node.type == "class_definition":
            element = self._extract_class(target_node)
            if element:
                element.decorators = decorators
                element.callable_type = CallableType.DECORATED_CLASS
                # Rebuild signature
                decorator_str = '\n'.join([f"@{dec}" for dec in decorators])
                element.signature = f"{decorator_str}\n{element.signature}"
            return element
        else:
            element = self._extract_function(target_node, class_name)
            if element:
                element.decorators = decorators
                element.callable_type = CallableType.DECORATED_FUNCTION
                # Rebuild signature
                decorator_str = '\n'.join([f"@{dec}" for dec in decorators])
                element.signature = f"{decorator_str}\n{element.signature}"
            return element
    
    def _extract_global_variables(self, root_node) -> List[CallableElement]:
        """Extract global variables and constants"""
        elements = []
        
        # Find assignment statements
        assignment_nodes = self._find_nodes_by_type(root_node, "assignment")
        
        for assignment in assignment_nodes:
            # Ensure it's a module-level assignment
            if self._is_module_level_assignment(assignment, root_node):
                var_elements = self._extract_assignment_variables(assignment)
                elements.extend(var_elements)
                
        return elements
    
    def _extract_assignment_variables(self, assignment_node) -> List[CallableElement]:
        """从赋值语句中提取变量"""
        elements = []
        
        # 获取左侧的标识符
        left_side = assignment_node.child_by_field_name("left")
        if not left_side:
            return elements
            
        # 处理不同类型的赋值左侧
        identifiers = self._extract_identifiers_from_assignment_left(left_side)
        
        code = self._get_node_text(assignment_node)
        
        for identifier in identifiers:
            # 判断是否是常量（全大写）
            is_constant = identifier.isupper() and '_' in identifier or len(identifier) > 1 and identifier.isupper()
            is_public = not identifier.startswith('_')
            
            callable_type = CallableType.CONSTANT if is_constant else CallableType.GLOBAL_VARIABLE
            
            elements.append(CallableElement(
                name=identifier,
                callable_type=callable_type,
                code=code,
                signature=f"{identifier} = ...",
                decorators=[],
                line_start=assignment_node.start_point[0] + 1,
                line_end=assignment_node.end_point[0] + 1,
                is_public=is_public
            ))
            
        return elements
    
    def _get_class_name(self, class_node) -> Optional[str]:
        """获取类名"""
        name_node = class_node.child_by_field_name("name")
        return self._get_node_text(name_node) if name_node else None
    
    def _get_decorators_for_node(self, node) -> List[str]:
        """获取节点的装饰器（针对没有decorated_definition包装的情况）"""
        decorators = []
        # 在tree-sitter中，装饰器通常作为前面的兄弟节点出现
        # 但这里我们主要处理已经在decorated_definition中的情况
        return decorators
    
    def _extract_docstring(self, node) -> Optional[str]:
        """提取文档字符串"""
        # 查找函数或类体中的第一个表达式语句
        body_node = node.child_by_field_name("body")
        if not body_node:
            return None
            
        for child in body_node.children:
            if child.type == "expression_statement":
                expr = child.children[0] if child.children else None
                if expr and expr.type == "string":
                    docstring = self._get_node_text(expr)
                    # 移除引号并处理转义
                    return self._clean_docstring(docstring)
                    
        return None
    
    def _clean_docstring(self, raw_docstring: str) -> str:
        """清理文档字符串"""
        # 移除外层引号
        if raw_docstring.startswith('"""') or raw_docstring.startswith("'''"):
            return raw_docstring[3:-3].strip()
        elif raw_docstring.startswith('"') or raw_docstring.startswith("'"):
            return raw_docstring[1:-1].strip()
        return raw_docstring
    
    def _get_base_classes(self, class_node) -> List[str]:
        """获取基类列表"""
        bases = []
        superclasses_node = class_node.child_by_field_name("superclasses")
        if superclasses_node:
            for child in superclasses_node.children:
                if child.type == "identifier":
                    bases.append(self._get_node_text(child))
                elif child.type == "attribute":
                    bases.append(self._get_node_text(child))
        return bases
    
    def _extract_parameters(self, function_node) -> List[str]:
        """提取函数参数"""
        parameters = []
        params_node = function_node.child_by_field_name("parameters")
        
        if params_node:
            for child in params_node.children:
                if child.type == "identifier":
                    parameters.append(self._get_node_text(child))
                elif child.type == "default_parameter":
                    name_node = child.child_by_field_name("name")
                    default_node = child.child_by_field_name("value")
                    if name_node:
                        param_name = self._get_node_text(name_node)
                        default_value = self._get_node_text(default_node) if default_node else "..."
                        parameters.append(f"{param_name}={default_value}")
                elif child.type == "typed_parameter":
                    name_node = child.child_by_field_name("name")
                    type_node = child.child_by_field_name("type")
                    if name_node:
                        param_name = self._get_node_text(name_node)
                        param_type = self._get_node_text(type_node) if type_node else ""
                        parameters.append(f"{param_name}: {param_type}" if param_type else param_name)
                elif child.type == "typed_default_parameter":
                    name_node = child.child_by_field_name("name")
                    type_node = child.child_by_field_name("type")
                    default_node = child.child_by_field_name("value")
                    if name_node:
                        param_name = self._get_node_text(name_node)
                        param_type = self._get_node_text(type_node) if type_node else ""
                        default_value = self._get_node_text(default_node) if default_node else "..."
                        type_str = f": {param_type}" if param_type else ""
                        parameters.append(f"{param_name}{type_str} = {default_value}")
                        
        return parameters
    
    def _extract_return_annotation(self, function_node) -> Optional[str]:
        """Extract return type annotation"""
        return_type_node = function_node.child_by_field_name("return_type")
        return self._get_node_text(return_type_node) if return_type_node else None
    
    def _determine_function_type(self, node, name: str, decorators: List[str], class_name: Optional[str]) -> CallableType:
        """Determine function type"""
        # Check if it's an async function
        is_async = node.type == "async_function_definition"
        
        # If not in a class, it's a regular function
        if not class_name:
            if decorators:
                return CallableType.DECORATED_FUNCTION
            return CallableType.ASYNC_FUNCTION if is_async else CallableType.FUNCTION
        
        # Functions in classes are methods
        # Check special decorators
        for decorator in decorators:
            if "staticmethod" in decorator:
                return CallableType.STATIC_METHOD
            elif "classmethod" in decorator:
                return CallableType.CLASS_METHOD
            elif "property" in decorator:
                return CallableType.PROPERTY
        
        # Check magic methods
        if name.startswith('__') and name.endswith('__'):
            return CallableType.MAGIC_METHOD
        
        # Check visibility
        if name.startswith('__'):
            return CallableType.PRIVATE_METHOD
        elif name.startswith('_'):
            return CallableType.PROTECTED_METHOD
        
        # Regular method
        if decorators:
            return CallableType.DECORATED_FUNCTION
        return CallableType.ASYNC_METHOD if is_async else CallableType.METHOD
    
    def _build_function_signature(self, node, name: str, parameters: List[str], 
                                 return_annotation: Optional[str], decorators: List[str]) -> str:
        """Build function signature"""
        is_async = node.type == "async_function_definition"
        
        # Build parameter string
        param_str = ", ".join(parameters) if parameters else ""
        
        # Build return type
        return_str = f" -> {return_annotation}" if return_annotation else ""
        
        # Build basic signature
        async_str = "async " if is_async else ""
        signature = f"{async_str}def {name}({param_str}){return_str}:"
        
        # Add decorators
        if decorators:
            decorator_str = '\n'.join([f"@{dec}" for dec in decorators])
            signature = f"{decorator_str}\n{signature}"
            
        return signature
    
    def _is_public_function(self, name: str, class_name: Optional[str]) -> bool:
        """Determine if function is public"""
        # Functions starting with single underscore are protected, double underscore are private
        # But magic methods (__init__ etc.) are public
        if name.startswith('__') and name.endswith('__'):
            return True  # Magic methods are public
        return not name.startswith('_')
    
    def _is_module_level_assignment(self, assignment_node, root_node) -> bool:
        """Check if assignment is at module level"""
        # Simple check: see if assignment's parent node is the root node
        parent = assignment_node.parent
        return parent == root_node
    
    def _extract_identifiers_from_assignment_left(self, left_node) -> List[str]:
        """Extract identifiers from assignment left side"""
        identifiers = []
        
        if left_node.type == "identifier":
            identifiers.append(self._get_node_text(left_node))
        elif left_node.type == "pattern_list":  # Tuple unpacking
            for child in left_node.children:
                if child.type == "identifier":
                    identifiers.append(self._get_node_text(child))
                    
        return identifiers
    
    def _find_nodes_by_type(self, root_node, node_types) -> List:
        """Find all nodes of specified types"""
        if isinstance(node_types, str):
            node_types = [node_types]
            
        result = []
        
        def traverse(node):
            if node.type in node_types:
                result.append(node)
            for child in node.children:
                traverse(child)
        
        traverse(root_node)
        return result
    
    def _find_direct_children_by_type(self, parent_node, node_types) -> List:
        """Find direct child nodes of specified types"""
        if isinstance(node_types, str):
            node_types = [node_types]
            
        result = []
        
        # Find class body
        body_node = parent_node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                if child.type in node_types:
                    result.append(child)
                    
        return result
    
    def _get_node_text(self, node) -> str:
        """Get text corresponding to node"""
        return self.code_bytes[node.start_byte:node.end_byte].decode('utf-8')
    
    def group_by_type(self, elements: List[CallableElement]) -> Dict[CallableType, List[CallableElement]]:
        """Group callable elements by type"""
        grouped = {}
        for element in elements:
            if element.callable_type not in grouped:
                grouped[element.callable_type] = []
            grouped[element.callable_type].append(element)
        return grouped
    
    def filter_public_only(self, elements: List[CallableElement]) -> List[CallableElement]:
        """Keep only public callable elements"""
        return [elem for elem in elements if elem.is_public]
    
    def filter_by_type(self, elements: List[CallableElement], types: List[CallableType]) -> List[CallableElement]:
        """Filter elements by specified types"""
        return [elem for elem in elements if elem.callable_type in types]
    
    def get_exported_elements(self, elements: List[CallableElement], 
                            all_names: Optional[List[str]] = None) -> List[CallableElement]:
        """Get exported elements (based on __all__ list)"""
        if all_names is None:
            # If no __all__, return all public elements
            return self.filter_public_only(elements)
        
        # Filter based on __all__
        all_names_set = set(all_names)
        return [elem for elem in elements if elem.name in all_names_set]

def main():
    """Example usage"""
    
    # Sample Python code
    sample_python_code = '''
"""
Example module for demonstrating callable element extraction
"""

import os
from typing import List, Optional

# Global constants
API_VERSION = "1.0.0"
MAX_CONNECTIONS = 100

# Global variables
_internal_cache = {}
debug_mode = False

def public_function(param1: str, param2: int = 10) -> str:
    """This is a public function"""
    return f"{param1}: {param2}"

async def async_function(data: List[str]) -> None:
    """Async function example"""
    pass

def _private_function():
    """Private function"""
    pass

@property
def decorated_function():
    """Decorated function"""
    return "decorated"

class PublicClass:
    """Public class example"""
    
    class_variable = "class_var"
    _protected_variable = "protected"
    
    def __init__(self, name: str):
        """Constructor"""
        self.name = name
        self._internal = None
    
    def public_method(self) -> str:
        """Public method"""
        return self.name
    
    def _protected_method(self):
        """Protected method"""
        return self._internal
    
    def __private_method(self):
        """Private method"""
        pass
    
    @staticmethod
    def static_method(value: int) -> int:
        """Static method"""
        return value * 2
    
    @classmethod
    def class_method(cls, name: str):
        """Class method"""
        return cls(name)
    
    @property
    def name_property(self) -> str:
        """Property"""
        return self.name
    
    async def async_method(self):
        """Async method"""
        pass
    
    def __str__(self) -> str:
        """Magic method"""
        return f"PublicClass({self.name})"

@dataclass
class DataClass:
    """Decorator class"""
    value: int
    name: str = "default"

class _PrivateClass:
    """Private class"""
    pass

# Lambda function
lambda_func = lambda x: x * 2

# Tuple unpacking assignment
a, b = 1, 2
'''
    
    # Create extractor and extract callable elements
    extractor = PythonCallableExtractor()
    callable_elements = extractor.extract_all_callable_elements(sample_python_code)
    
    print(f"Extracted {len(callable_elements)} callable elements:\n")
    
    # Display grouped by type
    grouped = extractor.group_by_type(callable_elements)
    
    for callable_type, elements in grouped.items():
        print(f"\n=== {callable_type.value.upper().replace('_', ' ')} ===")
        for element in elements:
            print(f"Name: {element.name}")
            print(f"Signature: {element.signature}")
            print(f"Lines: {element.line_start}-{element.line_end}")
            print(f"Decorators: {element.decorators}")
            print(f"Public: {element.is_public}")
            if element.class_name:
                print(f"Class name: {element.class_name}")
            if element.docstring:
                print(f"Doc: {element.docstring[:50]}...")
            if element.parameters:
                print(f"Parameters: {element.parameters}")
            print("Code:")
            print(element.code[:150] + "..." if len(element.code) > 150 else element.code)
            print("-" * 50)
    
    # Show only public elements
    print("\n\n=== Show only public callable elements ===")
    public_elements = extractor.filter_public_only(callable_elements)
    for element in public_elements:
        print(f"{element.callable_type.value}: {element.name}")
    
    # Show only functions and methods
    print("\n\n=== Show only functions and methods ===")
    function_types = [
        CallableType.FUNCTION, CallableType.ASYNC_FUNCTION, 
        CallableType.METHOD, CallableType.ASYNC_METHOD,
        CallableType.STATIC_METHOD, CallableType.CLASS_METHOD
    ]
    function_elements = extractor.filter_by_type(callable_elements, function_types)
    for element in function_elements:
        visibility = "public" if element.is_public else "private/protected"
        print(f"{element.callable_type.value} ({visibility}): {element.signature.split(':')[0]}")

if __name__ == "__main__":
    main()