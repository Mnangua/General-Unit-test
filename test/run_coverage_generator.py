#!/usr/bin/env python3
"""
Coverage-Based Test Generator
基于覆盖率的测试生成工具

这个工具可以：
1. 分析项目的测试覆盖率
2. 找到未覆盖的代码行
3. 使用LLM为未覆盖的代码生成测试用例
4. 自动确定测试文件的放置位置
5. 生成详细的覆盖率报告
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, List, Optional

# 添加项目根目录到Python路径
current_dir = Path(__file__).parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

from src.generate.unit_test_generator import CoverageBasedTestGenerator
from src.generate.coverage_analyzer import analyze_project_coverage
from src.capi_client import CopilotProxyLLMClient


class CoverageTestGeneratorCLI:
    """命令行界面"""
    
    def __init__(self):
        self.generator = None
        
    def run_interactive(self):
        """运行交互式界面"""
        print("=" * 60)
        print("Coverage-Based Test Generator")
        print("基于覆盖率的测试生成工具")
        print("=" * 60)
        
        # 获取项目信息
        project_root = self._get_project_root()
        language = self._get_language()
        
        # 创建生成器实例
        print("\n初始化测试生成器...")
        try:
            self.generator = CoverageBasedTestGenerator(project_root, language)
            print("✓ 测试生成器初始化成功")
        except Exception as e:
            print(f"✗ 初始化失败: {e}")
            return
        
        # 显示菜单
        while True:
            choice = self._show_menu()
            
            if choice == '1':
                self._analyze_coverage()
            elif choice == '2':
                self._generate_tests()
            elif choice == '3':
                self._generate_and_save_tests()
            elif choice == '4':
                self._generate_full_report()
            elif choice == '5':
                self._show_project_info()
            elif choice == '6':
                print("退出程序")
                break
            else:
                print("无效选择，请重新选择")
    
    def _get_project_root(self) -> str:
        """获取项目根目录"""
        while True:
            default_path = os.getcwd()
            project_path = input(f"请输入项目根目录 (默认: {default_path}): ").strip()
            
            if not project_path:
                project_path = default_path
            
            if os.path.exists(project_path):
                return project_path
            else:
                print(f"目录不存在: {project_path}")
    
    def _get_language(self) -> str:
        """获取编程语言"""
        while True:
            print("\n支持的编程语言:")
            print("1. Python")
            print("2. Java")
            
            choice = input("请选择编程语言 (1-2): ").strip()
            
            if choice == '1':
                return 'python'
            elif choice == '2':
                return 'java'
            else:
                print("无效选择，请重新选择")
    
    def _show_menu(self) -> str:
        """显示主菜单"""
        print("\n" + "=" * 40)
        print("请选择操作:")
        print("1. 分析覆盖率")
        print("2. 生成测试用例")
        print("3. 生成并保存测试用例")
        print("4. 生成完整报告")
        print("5. 显示项目信息")
        print("6. 退出")
        print("=" * 40)
        
        return input("请输入选择 (1-6): ").strip()
    
    def _analyze_coverage(self):
        """分析覆盖率"""
        print("\n正在分析项目覆盖率...")
        
        try:
            coverage_report = self.generator.coverage_analyzer.collect_coverage()
            
            print(f"\n覆盖率分析结果:")
            print(f"  总代码行数: {coverage_report.total_lines}")
            print(f"  已覆盖行数: {coverage_report.covered_lines}")
            print(f"  覆盖率: {coverage_report.coverage_percentage:.2f}%")
            print(f"  未覆盖行数: {len(coverage_report.uncovered_lines)}")
            
            if coverage_report.uncovered_lines:
                print(f"\n前10个未覆盖的代码段:")
                for i, uncovered in enumerate(coverage_report.uncovered_lines[:10], 1):
                    print(f"  {i}. {uncovered.file_path}:{uncovered.line_start} - {uncovered.code_snippet.strip()}")
            
        except Exception as e:
            print(f"✗ 覆盖率分析失败: {e}")
    
    def _generate_tests(self):
        """生成测试用例"""
        print("\n正在生成测试用例...")
        
        max_files = self._get_max_files()
        
        try:
            generated_tests = self.generator.generate_tests_for_project(max_files=max_files)
            
            if generated_tests:
                print(f"\n✓ 成功生成 {len(generated_tests)} 个测试文件:")
                for source_file, test in generated_tests.items():
                    print(f"  {source_file} -> {test.test_file_name}")
                    print(f"    推荐路径: {test.recommended_path}")
                    print(f"    覆盖行数: {test.uncovered_lines_count}")
                    print(f"    代码长度: {len(test.test_code)} 字符")
                    print()
            else:
                print("没有生成任何测试用例")
                
        except Exception as e:
            print(f"✗ 测试生成失败: {e}")
    
    def _generate_and_save_tests(self):
        """生成并保存测试用例"""
        print("\n正在生成并保存测试用例...")
        
        max_files = self._get_max_files()
        
        try:
            generated_tests = self.generator.generate_tests_for_project(max_files=max_files)
            
            if generated_tests:
                # 保存测试文件
                saved_files = self.generator.save_generated_tests(generated_tests)
                
                print(f"\n✓ 成功生成并保存 {len(saved_files)} 个测试文件:")
                for source_file, test_path in saved_files.items():
                    print(f"  {source_file} -> {test_path}")
            else:
                print("没有生成任何测试用例")
                
        except Exception as e:
            print(f"✗ 测试生成和保存失败: {e}")
    
    def _generate_full_report(self):
        """生成完整报告"""
        print("\n正在生成完整的覆盖率和测试生成报告...")
        
        try:
            report_path = self.generator.generate_coverage_report()
            print(f"✓ 报告已生成: {report_path}")
            
            # 询问是否打开报告
            if input("是否要查看报告内容? (y/n): ").lower() == 'y':
                try:
                    with open(report_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    print("\n" + "=" * 60)
                    print(content[:2000])  # 显示前2000个字符
                    if len(content) > 2000:
                        print("...(内容较长，已截取前2000字符)")
                    print("=" * 60)
                except Exception as e:
                    print(f"读取报告失败: {e}")
                    
        except Exception as e:
            print(f"✗ 报告生成失败: {e}")
    
    def _show_project_info(self):
        """显示项目信息"""
        if not self.generator:
            print("生成器未初始化")
            return
            
        print(f"\n项目信息:")
        print(f"  项目根目录: {self.generator.project_root}")
        print(f"  编程语言: {self.generator.language}")
        print(f"  LLM客户端: {type(self.generator.llm_client).__name__}")
        
        # 检查项目结构
        key_files = []
        if self.generator.language == 'python':
            for pattern in ['*.py', 'requirements.txt', 'setup.py', 'pyproject.toml']:
                key_files.extend(list(self.generator.project_root.glob(pattern)))
        elif self.generator.language == 'java':
            for pattern in ['pom.xml', 'build.gradle', 'src/main/java/**/*.java']:
                key_files.extend(list(self.generator.project_root.glob(pattern)))
        
        if key_files:
            print(f"  关键文件: {len(key_files)} 个")
            for file in key_files[:5]:  # 显示前5个
                print(f"    {file.relative_to(self.generator.project_root)}")
            if len(key_files) > 5:
                print(f"    ...(还有 {len(key_files) - 5} 个文件)")
    
    def _get_max_files(self) -> int:
        """获取最大处理文件数"""
        while True:
            try:
                max_files = input("请输入最大处理文件数 (默认: 5): ").strip()
                if not max_files:
                    return 5
                return int(max_files)
            except ValueError:
                print("请输入有效的数字")


def run_batch_mode():
    """批处理模式"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Coverage-based test generator")
    parser.add_argument("project_root", help="Project root directory")
    parser.add_argument("language", choices=["python", "java"], help="Programming language")
    parser.add_argument("--action", choices=["analyze", "generate", "save", "report"], 
                       default="report", help="Action to perform")
    parser.add_argument("--max-files", type=int, default=5, help="Maximum files to process")
    parser.add_argument("--output", help="Output file for report")
    
    args = parser.parse_args()
    
    # 创建生成器
    generator = CoverageBasedTestGenerator(args.project_root, args.language)
    
    if args.action == "analyze":
        # 只分析覆盖率
        coverage_report = generator.coverage_analyzer.collect_coverage()
        print(f"Coverage: {coverage_report.coverage_percentage:.2f}%")
        print(f"Uncovered lines: {len(coverage_report.uncovered_lines)}")
        
    elif args.action == "generate":
        # 生成测试但不保存
        generated_tests = generator.generate_tests_for_project(max_files=args.max_files)
        print(f"Generated {len(generated_tests)} test files")
        
    elif args.action == "save":
        # 生成并保存测试
        generated_tests = generator.generate_tests_for_project(max_files=args.max_files)
        saved_files = generator.save_generated_tests(generated_tests)
        print(f"Saved {len(saved_files)} test files")
        
    elif args.action == "report":
        # 生成完整报告
        output_file = args.output or "coverage_test_generation_report.md"
        report_path = generator.generate_coverage_report(output_file)
        print(f"Report saved: {report_path}")


def main():
    """主入口"""
    if len(sys.argv) > 1:
        # 批处理模式
        run_batch_mode()
    else:
        # 交互模式
        cli = CoverageTestGeneratorCLI()
        cli.run_interactive()


if __name__ == "__main__":
    main()
