import string
from typing import List, Tuple, Union, Dict, Optional
from dataclasses import dataclass

import tree_sitter_python
import tree_sitter_java
from tree_sitter import Language, Parser

w_space = set(string.whitespace.encode("utf-8"))

@dataclass
class ImportStatement:
    """表示一个import语句"""
    raw_statement: str      # 完整的import语句
    import_type: str        # "import" 或 "from_import" (Python) / "java_import" 或 "java_static_import" (Java)
    module_name: str        # 被导入的模块名
    imported_names: List[str]  # 被导入的具体名称
    alias: Optional[str] = None  # 别名
    line_number: int = 0    # 行号
    is_static: bool = False # 是否是静态导入 (Java)
    is_wildcard: bool = False # 是否是通配符导入 (Java)

def tokenize(file_bytes, node, whitespace=True):
    compound_lits = ("concatenated_string, string_array", "chained_string")
    n_bytes = len(file_bytes)
    tokens, types = [], []
    nodes = node.children
    while nodes:
        nxt = nodes.pop(0)
        if not nxt.children or (
            "string" in str(nxt.type) and str(nxt.type) not in compound_lits or "char" in str(nxt.type)
        ):
            start, finish = nxt.start_byte, nxt.end_byte
            if whitespace:
                # walk right to include right whitespace in token
                while finish < n_bytes:
                    if file_bytes[finish] not in w_space:
                        break
                    finish += 1

            tok = file_bytes[start:finish].decode("utf-8")
            if not tokens:  # indent first token to maintain relative space
                tok = (" " * nxt.start_point[1]) + tok

            tokens.append(tok)
            types.append(nxt.type)
            continue
        nodes = nxt.children + nodes

    return tokens, types


class BaseLangParser:
    def __init__(self, lang_pkg):
        self.language = Language(lang_pkg.language())
        self.parser = Parser(self.language)
        self.code_bytes = None
        self.tree = None

    def has_syntax_error(self, text_code: str) -> bool:
        string_bytes = bytes(text_code, "utf8")
        tree = self.parser.parse(string_bytes)
        return tree.root_node.has_error

    @staticmethod
    def post_traverse_target_type(node, type_set: Union[str, List], godeep=False):
        if isinstance(type_set, str):
            type_set = (type_set,)

        max_deep = 500
        results = []

        def post_traverse(_n, deep):
            if _n.type in type_set:
                results.append(_n)
                if not godeep:
                    return

            if deep > max_deep:
                return
            if _n.child_count < 1:
                return

            for child in _n.children:
                post_traverse(child, deep + 1)

        post_traverse(node, 0)

        return results

    @staticmethod
    def children_by_type(node, types):
        """
        Return children of node of type belonging to types
        """
        if isinstance(types, str):
            types = (types,)
        return [child for child in node.children if child.type in types]

    def span_select(self, node, indent=False) -> str:
        if not node:
            return ""
        select = self.code_bytes[node.start_byte : node.end_byte].decode("utf-8")
        if indent:
            return " " * node.start_point[1] + select
        return select

    def clean_comments(self, text_code):
        code_bytes = bytes(text_code, "utf8")
        tree = self.parser.parse(code_bytes)
        tokens, types = tokenize(code_bytes, tree.root_node, whitespace=True)
        comments_types = ("comment", "line_comment", "block_comment")
        noncomments = "".join(tok for tok, typ in zip(tokens, types) if typ not in comments_types)
        # delete empty lines
        lines = [line for line in noncomments.split("\n") if len(line.strip()) > 0]
        return "\n".join(lines)

    def get_node_str(self, node):
        start, finish = node.start_byte, node.end_byte
        while finish < len(self.code_bytes):
            if self.code_bytes[finish] not in w_space:
                break
            finish += 1
        return self.code_bytes[start:finish].decode("utf-8")

    def import_nodes(self, root):
        raise NotImplementedError

    def class_nodes(self, root):
        raise NotImplementedError

    def import_statements(self, text_code) -> List[str]:
        self.code_bytes = bytes(text_code, "utf8")
        self.tree = self.parser.parse(self.code_bytes)

        nodes = self.import_nodes(self.tree.root_node)
        statements = [self.get_node_str(_n).strip() for _n in nodes]
        return statements

class PythonParser(BaseLangParser):  
    def __init__(self):  
        super().__init__(tree_sitter_python)  
  
    def import_nodes(self, root):  
        # Python 的 import 和 from_import  
        return self.post_traverse_target_type(root, ["import_statement", "import_from_statement"], godeep=True)  
  
    def class_nodes(self, root):  
        return self.post_traverse_target_type(root, "class_definition", godeep=True)  

    def collect_all_imports(self, text_code: str) -> List[ImportStatement]:
        """
        收集所有的import语句，返回详细的ImportStatement列表
        
        Args:
            text_code: Python源代码字符串
            
        Returns:
            包含所有import语句详细信息的列表
        """
        self.code_bytes = bytes(text_code, "utf8")
        self.tree = self.parser.parse(self.code_bytes)
        
        import_statements = []
        
        # 获取所有import节点
        import_nodes = self.import_nodes(self.tree.root_node)
        
        for node in import_nodes:
            import_info = self._parse_import_node(node)
            if import_info:
                import_statements.append(import_info)
        
        return import_statements
    
    def _parse_import_node(self, node) -> Optional[ImportStatement]:
        """解析单个import节点"""
        raw_statement = self.get_node_str(node).strip()
        line_number = node.start_point[0] + 1
        
        if node.type == "import_statement":
            return self._parse_import_statement(node, raw_statement, line_number)
        elif node.type == "import_from_statement":
            return self._parse_from_import_statement(node, raw_statement, line_number)
        
        return None
    
    def _parse_import_statement(self, node, raw_statement: str, line_number: int) -> ImportStatement:
        """解析普通import语句: import module [as alias]"""
        imported_names = []
        module_name = ""
        alias = None
        
        # 查找导入的模块名和别名
        for child in node.children:
            if child.type == "dotted_name":
                module_name = self._get_dotted_name(child)
                imported_names.append(module_name)
            elif child.type == "aliased_import":
                # 处理 import module as alias
                name_node = child.child_by_field_name("name")
                alias_node = child.child_by_field_name("alias")
                if name_node:
                    if name_node.type == "dotted_name":
                        module_name = self._get_dotted_name(name_node)
                    else:
                        module_name = self.get_node_str(name_node)
                    imported_names.append(module_name)
                if alias_node:
                    alias = self.get_node_str(alias_node)
            elif child.type == "identifier":
                module_name = self.get_node_str(child)
                imported_names.append(module_name)
        
        return ImportStatement(
            raw_statement=raw_statement,
            import_type="import",
            module_name=module_name,
            imported_names=imported_names,
            alias=alias,
            line_number=line_number
        )
    
    def _parse_from_import_statement(self, node, raw_statement: str, line_number: int) -> ImportStatement:
        """解析from import语句: from module import name1, name2 [as alias]"""
        module_name = ""
        imported_names = []
        
        # 查找模块名
        module_node = node.child_by_field_name("module_name")
        if module_node:
            if module_node.type == "dotted_name":
                module_name = self._get_dotted_name(module_node)
            elif module_node.type == "relative_module":
                module_name = self.get_node_str(module_node)
            else:
                module_name = self.get_node_str(module_node)
        
        # 查找导入的名称
        name_node = node.child_by_field_name("name")
        if name_node:
            if name_node.type == "wildcard_import":
                imported_names.append("*")
            elif name_node.type == "dotted_name":
                imported_names.append(self._get_dotted_name(name_node))
            elif name_node.type == "identifier":
                imported_names.append(self.get_node_str(name_node))
            elif name_node.type == "import_list":
                # 处理多个导入名称
                for child in name_node.children:
                    if child.type == "identifier":
                        imported_names.append(self.get_node_str(child))
                    elif child.type == "aliased_import":
                        # 处理 from module import name as alias
                        import_name_node = child.child_by_field_name("name")
                        if import_name_node:
                            imported_names.append(self.get_node_str(import_name_node))
                    elif child.type == "dotted_name":
                        imported_names.append(self._get_dotted_name(child))
        
        return ImportStatement(
            raw_statement=raw_statement,
            import_type="from_import",
            module_name=module_name,
            imported_names=imported_names,
            line_number=line_number
        )
    
    def _get_dotted_name(self, node) -> str:
        """获取点分割的名称，如 package.module.submodule"""
        return self.get_node_str(node)

class JavaParser(BaseLangParser):  
    def __init__(self):  
        super().__init__(tree_sitter_java)  
  
    def import_nodes(self, root):  
        return self.post_traverse_target_type(root, "import_declaration", godeep=True)  
  
    def class_nodes(self, root):  
        return self.post_traverse_target_type(root, "class_declaration", godeep=True)  

    def collect_all_imports(self, text_code: str) -> List[ImportStatement]:
        self.code_bytes = bytes(text_code, "utf8")
        self.tree = self.parser.parse(self.code_bytes)
        
        import_statements = []
        
        # 获取所有import节点
        import_nodes = self.import_nodes(self.tree.root_node)
        
        for node in import_nodes:
            import_info = self._parse_java_import_node(node)
            if import_info:
                import_statements.append(import_info)
        
        return import_statements

    def _parse_java_import_node(self, node) -> Optional[ImportStatement]:
        """解析单个Java import节点"""
        raw_statement = self.get_node_str(node).strip()
        line_number = node.start_point[0] + 1
        
        if node.type == "import_declaration":
            return self._parse_java_import_declaration(node, raw_statement, line_number)
        
        return None
    
    def _parse_java_import_declaration(self, node, raw_statement: str, line_number: int) -> ImportStatement:
        """
        解析Java import声明
        支持的格式:
        - import package.ClassName;
        - import package.*;
        - import static package.ClassName.methodName;
        - import static package.ClassName.*;
        """
        module_name = ""
        imported_names = []
        is_static = False
        is_wildcard = False
        
        # 检查是否是静态导入
        for child in node.children:
            if child.type == "static" or self.get_node_str(child).strip() == "static":
                is_static = True
                break
        
        # 查找导入的包名和类名
        for child in node.children:
            if child.type == "scoped_identifier":
                # 处理完整的包.类名
                full_name = self.get_node_str(child)
                if full_name.endswith("*"):
                    # 通配符导入: package.*
                    is_wildcard = True
                    module_name = full_name[:-2]  # 移除.*
                    imported_names.append("*")
                else:
                    # 具体类或方法导入
                    parts = full_name.split(".")
                    if len(parts) > 1:
                        if is_static:
                            # 静态导入: package.ClassName.methodName
                            if len(parts) >= 3:
                                module_name = ".".join(parts[:-2])  # package
                                class_name = parts[-2]  # ClassName
                                method_name = parts[-1]  # methodName
                                imported_names.append(f"{class_name}.{method_name}")
                            else:
                                module_name = ".".join(parts[:-1])
                                imported_names.append(parts[-1])
                        else:
                            # 普通导入: package.ClassName
                            module_name = ".".join(parts[:-1])  # package
                            imported_names.append(parts[-1])   # ClassName
                    else:
                        # 单个名称
                        module_name = ""
                        imported_names.append(full_name)
                        
            elif child.type == "identifier":
                # 处理简单的标识符
                identifier = self.get_node_str(child)
                if identifier not in ["import", "static", ";"]:
                    if not module_name and not imported_names:
                        # 如果还没有找到模块名，这可能是一个简单的类名
                        imported_names.append(identifier)
                        
            elif child.type == "asterisk" or self.get_node_str(child).strip() == "*":
                # 通配符导入
                is_wildcard = True
                imported_names.append("*")
        
        # 确定导入类型
        if is_static:
            import_type = "java_static_import"
        else:
            import_type = "java_import"
        
        return ImportStatement(
            raw_statement=raw_statement,
            import_type=import_type,
            module_name=module_name,
            imported_names=imported_names,
            line_number=line_number,
            is_static=is_static,
            is_wildcard=is_wildcard
        )


# 测试用例  
if __name__ == "__main__":  
    # Python 示例代码，包含各种import语句
    python_code_with_imports = """  
import os  
import sys as system
from pathlib import Path
from typing import List, Dict, Optional
from . import local_module
from ..parent import parent_module
from collections import *
import numpy as np
from dataclasses import dataclass, field

class Test:
    def test(self):
        return 1

def example_function():
    pass
"""  

    python_parser = PythonParser()  
    
    # 测试原有的import_statements方法
    print("=== 原有的import_statements方法 ===")
    import_statements = python_parser.import_statements(python_code_with_imports)
    for i, stmt in enumerate(import_statements, 1):
        print(f"{i}. {stmt}")
    
    print(f"\n总共找到 {len(import_statements)} 个import语句\n")
    
    # 测试新的collect_all_imports方法
    print("=== 新的collect_all_imports方法 ===")
    detailed_imports = python_parser.collect_all_imports(python_code_with_imports)
    
    for imp in detailed_imports:
        print(f"行 {imp.line_number}: {imp.raw_statement}")
        print(f"  类型: {imp.import_type}")
        print(f"  模块: {imp.module_name}")
        print(f"  导入的名称: {imp.imported_names}")
        if imp.alias:
            print(f"  别名: {imp.alias}")
        print("-" * 40)

    # Java示例代码，包含各种import语句
    java_code_with_imports = """
package com.example.demo;

import java.util.List;
import java.util.ArrayList;
import java.util.*;
import java.io.File;
import static java.lang.Math.PI;
import static java.lang.Math.*;
import static com.example.utils.StringUtils.isEmpty;
import javax.annotation.Nullable;

public class Example {
    public static void main(String[] args) {
        List<String> list = new ArrayList<>();
        System.out.println(PI);
    }
}
"""


    # 测试Java import收集
    java_parser = JavaParser()
    java_imports = java_parser.collect_all_imports(java_code_with_imports)
    print(f"找到 {len(java_imports)} 个Java import语句:")
    
    for imp in java_imports:
        print(f"行 {imp.line_number}: {imp.raw_statement}")
        print(f"  类型: {imp.import_type}")
        print(f"  包名: {imp.module_name}")
        print(f"  导入名称: {imp.imported_names}")
        if imp.is_static:
            print(f"  静态导入: 是")
        if imp.is_wildcard:
            print(f"  通配符导入: 是")
        print("-" * 40)
