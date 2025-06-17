import os
import json
import re
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path
from dataclasses import dataclass

from src.search.search_related_codes import create_docker_related_code_searcher
from src.capi_client import CopilotProxyLLMClient
from src.generate.coverage_analyzer import create_docker_coverage_analyzer

from src.generate.coverage_prompts import (
    PYTHON_TEST_GENERATION_SYSTEM_PROMPT,
    JAVA_TEST_GENERATION_SYSTEM_PROMPT,
    TEST_GENERATION_USER_PROMPT,
)


@dataclass
class GeneratedTest:
    source_file: str
    test_code: str
    test_file_path: str
    uncovered_lines_count: int


class CoverageBasedTestGenerator:
    """基于覆盖率的测试生成器"""
    
    def __init__(self, container_name: str, images: str, language: str, llm_client=None, use_related_code_searcher=False):
        self.language = language.lower()
        self.llm_client = llm_client
        self.container = container_name
        self.image = images
        self.use_related_code_searcher = use_related_code_searcher

        self.coverage_analyzer = create_docker_coverage_analyzer(
            container_name=self.container,
            docker_image=self.image,
        )
        
        if  self.use_related_code_searcher:
            # 使用Docker环境的相关代码搜索器
            self.code_searcher = create_docker_related_code_searcher(
                project_root="/testbed",  # Docker容器中的项目根目录
                language=self.language,
                llm_client=self.llm_client,
                container_name=self.container,
                docker_image=self.image,
                testbed_path="/testbed"
            )
        else:
            self.code_searcher = None
        
    def generate_tests_for_project(self):
        """为整个项目生成基于覆盖率的测试"""
        print(f"Starting coverage-based test generation for {self.language} project...")
        
        # 1. 收集覆盖率数据
        print("Step 1: Collecting coverage data...")
        coverage_report = self.coverage_analyzer.collect_coverage()
        
        if not coverage_report.uncovered_lines:
            print("No uncovered lines found.")
            return {}, coverage_report
        
        # 4. 为每个文件生成测试
        print("Step 3: Generating tests for uncovered code...")
        generated_tests = {}

        for uncovered in coverage_report.uncovered_lines:
            # dict - file_path, code, uncovered_lines
            file_path = uncovered.get("file_path", "")
            source_code = uncovered.get("code", "")
            uncovered_lines = uncovered.get("uncovered_lines", [])
            
            try:
                test = self._generate_test_for_file(file_path, source_code, uncovered_lines)
                if test:
                    generated_tests[test.test_file_path] = test.test_code
                    print(f"  ✓ Generated test in {test.test_file_path}, the test code: {test.test_code[:50]}...")
                else:
                    print(f"  ✗ Failed to generate test")
            except Exception as e:
                print(f"  ✗ Error generating test: {e}")
        
        return generated_tests, coverage_report
    
    def _generate_test_for_file(self, file_path, code, uncovered_lines):
        try:
            if not code:
                return None
            
            print(f"    Searching for related code context...")
            if self.code_searcher:
                related_code = self.code_searcher.search_related_codes(file_path, max_depth=4)
            else:
                related_code = ""
                print(f"    Warning: Code searcher not available, using empty context")

            print(f"    Generating test code using LLM...")
            test_code, test_file_path = self._call_llm_for_test_generation(
                file_path, code, uncovered_lines, related_code
            )
            
            if not test_code:
                return None
            
            # 如果没有获得文件路径，生成默认路径
            if not test_file_path:
                test_file_path = self._generate_default_test_file_path(file_path)
            
            return GeneratedTest(
                source_file=file_path,
                test_code=test_code,
                test_file_path=test_file_path,
                uncovered_lines_count=len(uncovered_lines)
            )
            
        except Exception as e:
            print(f"    Error in _generate_test_for_file: {e}")
            return None
    
    def _call_llm_for_test_generation(self, file_path: str, target_content: str, 
                                    uncovered_descriptions: str, related_code: str) -> Tuple[str, str]:
        """调用LLM生成测试代码，返回(test_code, test_file_path)"""
        try:
            # 选择合适的系统提示词
            if self.language == "python":
                system_prompt = PYTHON_TEST_GENERATION_SYSTEM_PROMPT
            elif self.language == "java":
                system_prompt = JAVA_TEST_GENERATION_SYSTEM_PROMPT
            else:
                system_prompt = f"Generate comprehensive unit tests for {self.language} code."
            
            # 构建用户提示词
            user_prompt = TEST_GENERATION_USER_PROMPT.format(
                LANGUAGE=self.language,
                TARGET_FILE_PATH=file_path,
                TARGET_FILE_CONTENT=target_content,
                UNCOVERED_LINES_DESCRIPTION=uncovered_descriptions,
                RELATED_CODE_CONTEXT=related_code
            )
            
            # 调用LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            response = self.llm_client.query(messages)
            print(f"    LLM response: {response}")
            return self._extract_test_from_json_response(response)
            
        except Exception as e:
            print(f"    Error got test code from llm: {e}")
            return "", ""
    
    def _extract_test_from_json_response(self, response: str) -> Tuple[str, str]:

        try:
            pattern = r'```json\n(.*?)\n```'   
            match = re.search(pattern, response.strip(), re.DOTALL)  
            if match:   
                data = json.loads(match.group(1))
                return data.get("test_code", ""), data.get("test_file_path", "")
            else:
                data = json.loads(response.strip())
                return data.get("test_code", ""), data.get("test_file_path", "")
        except json.JSONDecodeError:
            print("    Response is not valid JSON, trying to extract test code directly...")
            return "", ""
            
        
    def _generate_default_test_file_path(self, source_file: str) -> str:
        """生成默认的测试文件路径"""
        file_path = Path(source_file)
        base_name = file_path.stem
        
        if self.language == "python":
            return f"tests/test_{base_name}_extra.py"
        elif self.language == "java":
            # 将文件名转换为类名格式
            class_name = ''.join(word.capitalize() for word in base_name.split('_'))
            # 假设遵循Maven/Gradle项目结构
            return f"src/test/java/{class_name}ExtraTest.java"
        else:
            return f"tests/test_{base_name}_extra.{file_path.suffix[1:]}"

    def save_generated_tests(self, generated_tests):

        for file_path, code in generated_tests.items():
            try:
                # 获取Docker运行器
                docker_runner = self.coverage_analyzer.docker_runner
                if not docker_runner:
                    print(f"✗ Error: No Docker runner available for saving test files")
                    continue
                
                # 写入测试文件到容器
                success = docker_runner.write_file_to_container(code, file_path)
                
                if success:
                    print(f"✓ Saved test file to container: {file_path}")
                else:
                    print(f"✗ Failed to save test file to container: {file_path}")
                
            except Exception as e:
                print(f"✗ Error saving test for {file_path}: {e}")
        



# if __name__ == "__main__":
#     import argparse
    
#     parser = argparse.ArgumentParser(description="Generate tests based on coverage analysis")
#     parser.add_argument("--container", default="coverage_analyzer", help="Docker container name (for docker mode)")
#     parser.add_argument("--image", 
#                        default="codeexecservice.azurecr.io/pythontestgen.eval.x86_64.larq-zookeeper-v1:msbench-0.0.0",
#                        help="Docker image name")
#     parser.add_argument("--language", choices=["python", "java"], help="Programming language")
#     parser.add_argument("--model", default="claude-3.7-sonnet", help="LLM model to use")
#     parser.add_argument("--use-related-searcher", action="store_true", 
#                        help="Use related code searcher for better context")
    
#     args = parser.parse_args()

#     llm_client = CopilotProxyLLMClient(model=args.model)
    
#     # 创建测试生成器
#     generator = CoverageBasedTestGenerator(
#         container_name=args.container, 
#         images=args.image, 
#         language=args.language, 
#         llm_client=llm_client,
#         use_related_code_searcher=args.use_related_searcher
#     )
    
#     generated_tests, coverage_report = generator.generate_tests_for_project()

#     if generated_tests:
#         generator.save_generated_tests(generated_tests)
