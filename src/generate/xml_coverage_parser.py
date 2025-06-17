#!/usr/bin/env python3
"""
XML Coverage Parser - 在Docker容器内部执行的XML覆盖率解析脚本
"""

import os
import json
import sys
import xml.etree.ElementTree as ET
from typing import Dict, List, Any
from pathlib import Path


class CoverageXMLParser:
    """在Docker容器内部解析XML覆盖率报告"""
    
    def __init__(self, testbed_path: str = "/testbed"):
        self.testbed_path = testbed_path
    
    def parse_xml_coverage(self, xml_path: str) -> Dict[str, Any]:
        """解析XML覆盖率报告并返回结构化数据"""
        uncovered_code = []
        coverage_summary = {}
        
        if not os.path.exists(xml_path):
            return {
                "error": f"Coverage XML file not found: {xml_path}",
                "uncovered_code": [],
                "coverage_summary": {}
            }
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            # 解析覆盖率摘要信息
            coverage_summary = self._extract_coverage_summary(root)
            
            # 解析未覆盖的代码行
            for package in root.findall('.//package'):
                package_name = package.get('name', '')
                
                for class_elem in package.findall('classes/class'):
                    filename = class_elem.get('filename', '')
                    class_name = class_elem.get('name', '')
                    
                    # 只处理Python文件
                    if not filename.endswith('.py'):
                        continue
                    
                    # 处理未覆盖的行
                    for line in class_elem.findall('lines/line'):
                        hits = int(line.get('hits', '0'))
                        line_number = int(line.get('number', '0'))
                        is_branch = line.get('branch', 'false') == 'true'
                        
                        if hits == 0:  # 未覆盖的行
                            code_snippet = self._get_code_snippet(filename, line_number)
                            if code_snippet and self._is_meaningful_code(code_snippet):
                                uncovered_info = {
                                    "file_path": filename,
                                    "line_start": line_number,
                                    "line_end": line_number,
                                    "code_snippet": code_snippet,
                                    "coverage_type": "branch" if is_branch else "line",
                                    "function_name": self._extract_function_name(filename, line_number),
                                    "class_name": class_name,
                                    "package_name": package_name
                                }
                                uncovered_code.append(uncovered_info)
            
            return {
                "uncovered_code": uncovered_code,
                "coverage_summary": coverage_summary,
                "success": True
            }
            
        except Exception as e:
            return {
                "error": f"Error parsing XML coverage: {str(e)}",
                "uncovered_code": [],
                "coverage_summary": {},
                "success": False
            }
    
    def _extract_coverage_summary(self, root) -> Dict[str, Any]:
        """提取覆盖率摘要信息"""
        summary = {}
        
        try:
            # 尝试从根元素获取总体覆盖率信息
            for package in root.findall('.//package'):
                package_name = package.get('name', 'overall')
                
                # 计算行覆盖率
                lines_covered = 0
                lines_valid = 0
                
                for class_elem in package.findall('classes/class'):
                    for line in class_elem.findall('lines/line'):
                        lines_valid += 1
                        hits = int(line.get('hits', '0'))
                        if hits > 0:
                            lines_covered += 1
                
                if lines_valid > 0:
                    line_coverage = (lines_covered / lines_valid) * 100
                    summary[package_name] = {
                        "lines_covered": lines_covered,
                        "lines_valid": lines_valid,
                        "line_coverage_percentage": round(line_coverage, 2)
                    }
        
        except Exception as e:
            summary["error"] = f"Error extracting summary: {str(e)}"
        
        return summary
    
    def _get_code_snippet(self, file_path: str, line_number: int) -> str:
        """获取指定行的代码片段"""
        try:
            # 处理相对路径
            if not file_path.startswith('/'):
                full_path = os.path.join(self.testbed_path, file_path)
            else:
                full_path = file_path
            
            if not os.path.exists(full_path):
                return ""
            
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                if 1 <= line_number <= len(lines):
                    return lines[line_number - 1].rstrip()
        except Exception as e:
            print(f"Error reading code snippet from {file_path}:{line_number}: {e}", file=sys.stderr)
        return ""
    
    def _is_meaningful_code(self, code_snippet: str) -> bool:
        """判断是否是有意义的代码行（不是注释或空行）"""
        if not code_snippet:
            return False
        
        stripped_code = code_snippet.strip()
        
        # 过滤掉无意义的行
        meaningless_patterns = [
            '',  # 空行
            'pass',  # pass语句
            '...',  # 省略号
        ]
        
        if stripped_code in meaningless_patterns:
            return False
        
        # 过滤掉注释
        if (stripped_code.startswith('#') or 
            stripped_code.startswith('"""') or 
            stripped_code.startswith("'''") or
            stripped_code.endswith('"""') or
            stripped_code.endswith("'''")):
            return False
        
        return True
    
    def _extract_function_name(self, file_path: str, line_number: int) -> str:
        """尝试提取包含该行的函数名"""
        try:
            full_path = os.path.join(self.testbed_path, file_path) if not file_path.startswith('/') else file_path
            
            if not os.path.exists(full_path):
                return ""
            
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # 向上查找最近的函数定义
            for i in range(line_number - 1, -1, -1):
                if i < len(lines):
                    line = lines[i].strip()
                    if line.startswith('def ') and ':' in line:
                        # 提取函数名
                        func_def = line[4:].split('(')[0].strip()
                        return func_def
            
        except Exception:
            pass
        
        return ""


def main():
    """主函数，用于命令行调用"""
    if len(sys.argv) < 2:
        print("Usage: python xml_coverage_parser.py <xml_file_path> [testbed_path]")
        sys.exit(1)
    
    xml_file_path = sys.argv[1]
    testbed_path = sys.argv[2] if len(sys.argv) > 2 else "/testbed"
    
    parser = CoverageXMLParser(testbed_path)
    result = parser.parse_xml_coverage(xml_file_path)
    
    # 输出JSON格式的结果
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
