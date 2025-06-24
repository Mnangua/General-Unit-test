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
    """表示一个可被调用的Python代码元素"""
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
    """Python代码可调用元素提取器"""
    
    def __init__(self):
        self.language = Language(tree_sitter_python.language())
        self.parser = Parser(self.language)
        self.code = ""
        self.code_bytes = b""
        self.code_lines = []
        
    def extract_all_callable_elements(self, python_code: str) -> List[CallableElement]:
        """
        提取Python代码中所有可能被其他代码调用的元素
        
        Args:
            python_code: 完整的Python源代码字符串
            
        Returns:
            包含所有可调用元素的列表
        """
        self.code = python_code
        self.code_bytes = python_code.encode('utf-8')
        self.code_lines = python_code.split('\n')
        tree = self.parser.parse(self.code_bytes)
        root_node = tree.root_node
        
        callable_elements = []
        
        # 提取模块级别的可调用元素
        callable_elements.extend(self._extract_module_level_elements(root_node))
        
        # 提取类和其成员
        callable_elements.extend(self._extract_classes_and_members(root_node))
        
        # 提取全局变量和常量
        callable_elements.extend(self._extract_global_variables(root_node))
        
        return callable_elements
    
    def _extract_module_level_elements(self, root_node) -> List[CallableElement]:
        """提取模块级别的函数和类"""
        elements = []
        
        # 查找模块级别的函数定义
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
        """提取类及其成员方法"""
        elements = []
        
        class_nodes = self._find_nodes_by_type(root_node, "class_definition")
        
        for class_node in class_nodes:
            class_name = self._get_class_name(class_node)
            
            # 提取类中的方法
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
        """提取类定义"""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
            
        name = self._get_node_text(name_node)
        code = self._get_node_text(node)
        
        # 获取装饰器
        decorators = self._get_decorators_for_node(node)
        
        # 获取文档字符串
        docstring = self._extract_docstring(node)
        
        # 获取基类
        bases = self._get_base_classes(node)
        
        # 构建签名
        base_str = f"({', '.join(bases)})" if bases else ""
        decorator_str = '\n'.join([f"@{dec}" for dec in decorators])
        signature = f"{decorator_str}\nclass {name}{base_str}:".strip()
        
        # 判断是否是公有类
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
        """提取函数或方法定义"""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
            
        name = self._get_node_text(name_node)
        code = self._get_node_text(node)
        
        # 获取装饰器
        decorators = self._get_decorators_for_node(node)
        
        # 获取文档字符串
        docstring = self._extract_docstring(node)
        
        # 获取参数
        parameters = self._extract_parameters(node)
        
        # 获取返回类型注解
        return_annotation = self._extract_return_annotation(node)
        
        # 确定函数类型
        callable_type = self._determine_function_type(node, name, decorators, class_name)
        
        # 构建签名
        signature = self._build_function_signature(node, name, parameters, return_annotation, decorators)
        
        # 判断可见性
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
        """提取装饰器定义"""
        # 查找装饰器节点
        decorators = []
        target_node = None
        
        for child in node.children:
            if child.type == "decorator":
                decorator_text = self._get_node_text(child)[1:]  # 移除@符号
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
                # 重新构建签名
                decorator_str = '\n'.join([f"@{dec}" for dec in decorators])
                element.signature = f"{decorator_str}\n{element.signature}"
            return element
        else:
            element = self._extract_function(target_node, class_name)
            if element:
                element.decorators = decorators
                element.callable_type = CallableType.DECORATED_FUNCTION
                # 重新构建签名
                decorator_str = '\n'.join([f"@{dec}" for dec in decorators])
                element.signature = f"{decorator_str}\n{element.signature}"
            return element
    
    def _extract_global_variables(self, root_node) -> List[CallableElement]:
        """提取全局变量和常量"""
        elements = []
        
        # 查找赋值语句
        assignment_nodes = self._find_nodes_by_type(root_node, "assignment")
        
        for assignment in assignment_nodes:
            # 确保是模块级别的赋值
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
        """提取返回类型注解"""
        return_type_node = function_node.child_by_field_name("return_type")
        return self._get_node_text(return_type_node) if return_type_node else None
    
    def _determine_function_type(self, node, name: str, decorators: List[str], class_name: Optional[str]) -> CallableType:
        """确定函数类型"""
        # 检查是否是异步函数
        is_async = node.type == "async_function_definition"
        
        # 如果不在类中，就是普通函数
        if not class_name:
            if decorators:
                return CallableType.DECORATED_FUNCTION
            return CallableType.ASYNC_FUNCTION if is_async else CallableType.FUNCTION
        
        # 在类中的函数是方法
        # 检查特殊装饰器
        for decorator in decorators:
            if "staticmethod" in decorator:
                return CallableType.STATIC_METHOD
            elif "classmethod" in decorator:
                return CallableType.CLASS_METHOD
            elif "property" in decorator:
                return CallableType.PROPERTY
        
        # 检查魔术方法
        if name.startswith('__') and name.endswith('__'):
            return CallableType.MAGIC_METHOD
        
        # 检查可见性
        if name.startswith('__'):
            return CallableType.PRIVATE_METHOD
        elif name.startswith('_'):
            return CallableType.PROTECTED_METHOD
        
        # 普通方法
        if decorators:
            return CallableType.DECORATED_FUNCTION
        return CallableType.ASYNC_METHOD if is_async else CallableType.METHOD
    
    def _build_function_signature(self, node, name: str, parameters: List[str], 
                                 return_annotation: Optional[str], decorators: List[str]) -> str:
        """构建函数签名"""
        is_async = node.type == "async_function_definition"
        
        # 构建参数字符串
        param_str = ", ".join(parameters) if parameters else ""
        
        # 构建返回类型
        return_str = f" -> {return_annotation}" if return_annotation else ""
        
        # 构建基本签名
        async_str = "async " if is_async else ""
        signature = f"{async_str}def {name}({param_str}){return_str}:"
        
        # 添加装饰器
        if decorators:
            decorator_str = '\n'.join([f"@{dec}" for dec in decorators])
            signature = f"{decorator_str}\n{signature}"
            
        return signature
    
    def _is_public_function(self, name: str, class_name: Optional[str]) -> bool:
        """判断函数是否是公有的"""
        # 以单下划线开头的是受保护的，双下划线是私有的
        # 但魔术方法（__init__等）是公有的
        if name.startswith('__') and name.endswith('__'):
            return True  # 魔术方法是公有的
        return not name.startswith('_')
    
    def _is_module_level_assignment(self, assignment_node, root_node) -> bool:
        """检查赋值是否在模块级别"""
        # 简单检查：看看赋值的父节点是否是根节点
        parent = assignment_node.parent
        return parent == root_node
    
    def _extract_identifiers_from_assignment_left(self, left_node) -> List[str]:
        """从赋值左侧提取标识符"""
        identifiers = []
        
        if left_node.type == "identifier":
            identifiers.append(self._get_node_text(left_node))
        elif left_node.type == "pattern_list":  # 元组解包
            for child in left_node.children:
                if child.type == "identifier":
                    identifiers.append(self._get_node_text(child))
                    
        return identifiers
    
    def _find_nodes_by_type(self, root_node, node_types) -> List:
        """查找指定类型的所有节点"""
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
        """查找直接子节点中指定类型的节点"""
        if isinstance(node_types, str):
            node_types = [node_types]
            
        result = []
        
        # 查找类体
        body_node = parent_node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                if child.type in node_types:
                    result.append(child)
                    
        return result
    
    def _get_node_text(self, node) -> str:
        """获取节点对应的文本"""
        return self.code_bytes[node.start_byte:node.end_byte].decode('utf-8')
    
    def group_by_type(self, elements: List[CallableElement]) -> Dict[CallableType, List[CallableElement]]:
        """按类型分组可调用元素"""
        grouped = {}
        for element in elements:
            if element.callable_type not in grouped:
                grouped[element.callable_type] = []
            grouped[element.callable_type].append(element)
        return grouped
    
    def filter_public_only(self, elements: List[CallableElement]) -> List[CallableElement]:
        """只保留公有的可调用元素"""
        return [elem for elem in elements if elem.is_public]
    
    def filter_by_type(self, elements: List[CallableElement], types: List[CallableType]) -> List[CallableElement]:
        """按类型过滤元素"""
        return [elem for elem in elements if elem.callable_type in types]
    
    def get_exported_elements(self, elements: List[CallableElement], 
                            all_names: Optional[List[str]] = None) -> List[CallableElement]:
        """获取导出的元素（基于__all__列表）"""
        if all_names is None:
            # 如果没有__all__，返回所有公有元素
            return self.filter_public_only(elements)
        
        # 根据__all__过滤
        all_names_set = set(all_names)
        return [elem for elem in elements if elem.name in all_names_set]

def main():
    """示例使用"""
    
    # 示例Python代码
    sample_python_code = '''
"""
示例模块用于演示可调用元素提取
"""

import os
from typing import List, Optional

# 全局常量
API_VERSION = "1.0.0"
MAX_CONNECTIONS = 100

# 全局变量
_internal_cache = {}
debug_mode = False

def public_function(param1: str, param2: int = 10) -> str:
    """这是一个公有函数"""
    return f"{param1}: {param2}"

async def async_function(data: List[str]) -> None:
    """异步函数示例"""
    pass

def _private_function():
    """私有函数"""
    pass

@property
def decorated_function():
    """装饰器函数"""
    return "decorated"

class PublicClass:
    """公有类示例"""
    
    class_variable = "class_var"
    _protected_variable = "protected"
    
    def __init__(self, name: str):
        """构造函数"""
        self.name = name
        self._internal = None
    
    def public_method(self) -> str:
        """公有方法"""
        return self.name
    
    def _protected_method(self):
        """受保护方法"""
        return self._internal
    
    def __private_method(self):
        """私有方法"""
        pass
    
    @staticmethod
    def static_method(value: int) -> int:
        """静态方法"""
        return value * 2
    
    @classmethod
    def class_method(cls, name: str):
        """类方法"""
        return cls(name)
    
    @property
    def name_property(self) -> str:
        """属性"""
        return self.name
    
    async def async_method(self):
        """异步方法"""
        pass
    
    def __str__(self) -> str:
        """魔术方法"""
        return f"PublicClass({self.name})"

@dataclass
class DataClass:
    """装饰器类"""
    value: int
    name: str = "default"

class _PrivateClass:
    """私有类"""
    pass

# Lambda函数
lambda_func = lambda x: x * 2

# 元组解包赋值
a, b = 1, 2
'''
    
    # 创建提取器并提取可调用元素
    extractor = PythonCallableExtractor()
    callable_elements = extractor.extract_all_callable_elements(sample_python_code)
    
    print(f"提取到 {len(callable_elements)} 个可调用元素:\n")
    
    # 按类型分组显示
    grouped = extractor.group_by_type(callable_elements)
    
    for callable_type, elements in grouped.items():
        print(f"\n=== {callable_type.value.upper().replace('_', ' ')} ===")
        for element in elements:
            print(f"名称: {element.name}")
            print(f"签名: {element.signature}")
            print(f"行数: {element.line_start}-{element.line_end}")
            print(f"装饰器: {element.decorators}")
            print(f"公有: {element.is_public}")
            if element.class_name:
                print(f"类名: {element.class_name}")
            if element.docstring:
                print(f"文档: {element.docstring[:50]}...")
            if element.parameters:
                print(f"参数: {element.parameters}")
            print("代码:")
            print(element.code[:150] + "..." if len(element.code) > 150 else element.code)
            print("-" * 50)
    
    # 只显示公有元素
    print("\n\n=== 只显示公有可调用元素 ===")
    public_elements = extractor.filter_public_only(callable_elements)
    for element in public_elements:
        print(f"{element.callable_type.value}: {element.name}")
    
    # 只显示函数和方法
    print("\n\n=== 只显示函数和方法 ===")
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