import os
import json
import re
from typing import List, Set, Dict, Tuple
from pathlib import Path

from src.utils import DockerCommandRunner
from src.capi_client import CopilotProxyLLMClient
from src.search.prompts import (
    SEARCH_DEPENDENT_FILES_SYSTEM_PROMPT,
    SEARCH_DEPENDENT_FILES_USER_PROMPT,
    SEARCH_DEPENDENT_FILES_EXTRA_USER_PROMPT,
    SEARCH_DEPENDENT_CODES_SYSTEM_PROMPT,
    SEARCH_DEPENDENT_CODES_USER_PROMPT
)

class RelatedCodeSearcher:
    """搜索相关代码的主类"""
    
    def __init__(self, project_root: str, language: str = "auto", llm_client=None, docker_runner: DockerCommandRunner = None):
        """
        初始化搜索器
        
        Args:
            project_root: 项目根目录路径（在Docker容器中的路径）
            language: 编程语言 ("java", "python", "c#", "typescript", "auto")
            llm_client: LLM客户端，需要实现query方法
            docker_runner: Docker命令运行器，用于在容器中执行命令
        """
        self.project_root = Path(project_root).resolve()
        self.language = language.lower()
        self.llm_client = llm_client or (CopilotProxyLLMClient() if CopilotProxyLLMClient else None)
        self.docker_runner = docker_runner
        
        if not self.docker_runner:
            raise ValueError("Docker runner is required for this implementation")
        
        # 语言对应的文件扩展名映射
        self.language_extensions = {
            "java": [".java"],
            "python": [".py", ".pyx", ".pyi"],
            "c#": [".cs"],
            "csharp": [".cs"],
            "typescript": [".ts", ".tsx"],
            "javascript": [".js", ".jsx"],
            "cpp": [".cpp", ".cxx", ".cc", ".hpp", ".h"],
            "c": [".c", ".h"],
            "go": [".go"],
            "rust": [".rs"],
            "kotlin": [".kt", ".kts"],
            "scala": [".scala"],
            "php": [".php"],
            "ruby": [".rb"],
            "swift": [".swift"]
        }
        
        # 语言对应的特殊文件名映射
        self.language_special_files = {
            "python": ["__init__.py"],
            "java": ["package-info.java"],
            "javascript": ["index.js"],
            "typescript": ["index.ts"],
            "c#": ["AssemblyInfo.cs"],
            "csharp": ["AssemblyInfo.cs"]
        }
        
    def get_project_tree_structure(self) -> str:
        """获取项目树结构，根据语言过滤相关文件"""
        try:
            # 获取当前语言的文件扩展名
            extensions = self._get_current_extensions()
            
            # Docker环境中的处理
            return self._get_docker_tree_structure(extensions)
                
        except Exception as e:
            print(f"Warning: Failed to get tree structure: {e}")
            return self._generate_tree_structure_fallback()
    
    def _get_docker_tree_structure(self, extensions: List[str]) -> str:
        """在Docker环境中获取项目树结构"""
        try:
            # 首先尝试安装tree命令（如果不存在）
            install_result = self.docker_runner.run_command("which tree || (apt-get update && apt-get install -y tree)")
            
            if extensions:
                # 构建tree命令的pattern
                patterns = [f"*{ext}" for ext in extensions]
                pattern_str = " -o ".join([f"-P '{p}'" for p in patterns])
                command = f"tree {pattern_str} --prune"
            else:
                # 如果语言未指定或为auto，显示所有文件
                command = "tree"
            
            result = self.docker_runner.run_command(command)
            
            if result.get("stdout") and result.get("returncode") == 0:
                return result["stdout"]
            else:
                # 如果tree命令失败，使用find命令作为备选
                return self._get_docker_find_structure(extensions)
                
        except Exception as e:
            print(f"Warning: Docker tree command failed: {e}")
            return self._get_docker_find_structure(extensions)
    
    def _get_docker_find_structure(self, extensions: List[str]) -> str:
        """使用find命令在Docker中获取文件结构"""
        try:
            if extensions:
                # 构建find命令的文件类型过滤
                name_patterns = [f"-name '*{ext}'" for ext in extensions]
                find_pattern = " -o ".join(name_patterns)
                command = f"find . -type f \\( {find_pattern} \\) | sort"
            else:
                # 显示所有文件，但排除常见的隐藏目录
                command = "find . -type f -not -path './.git/*' -not -path './.*' | sort"
            
            result = self.docker_runner.run_command(command)
            
            if result.get("stdout") and result.get("returncode") == 0:
                # 将find的输出转换为类似tree的格式
                return self._format_find_output_as_tree(result["stdout"])
            else:
                return self._generate_tree_structure_fallback()
                
        except Exception as e:
            print(f"Warning: Docker find command failed: {e}")
            return self._generate_tree_structure_fallback()
    
    
    def _format_find_output_as_tree(self, find_output: str) -> str:
        """将find命令的输出格式化为类似tree的结构"""
        lines = [line.strip() for line in find_output.split('\n') if line.strip()]
        if not lines:
            return ""
        
        # 构建目录结构
        tree_lines = ["Project Structure:"]
        processed_paths = set()
        
        # 按路径深度和字母顺序排序
        lines.sort(key=lambda x: (x.count('/'), x))
        
        for line in lines:
            # 移除前导的./
            path = line.lstrip('./')
            if not path or path in processed_paths:
                continue
                
            processed_paths.add(path)
            parts = path.split('/')
            
            # 构建树状结构显示
            depth = len(parts) - 1
            indent = "  " * depth
            filename = parts[-1]
            
            if depth == 0:
                tree_lines.append(f"├── {filename}")
            else:
                tree_lines.append(f"{indent}├── {filename}")
        
        return '\n'.join(tree_lines)
    
    def _get_current_extensions(self) -> List[str]:
        """获取当前语言的文件扩展名"""
        if self.language == "auto":
            return []
        return self.language_extensions.get(self.language, [])
    
    def _generate_tree_structure_fallback(self) -> str:
        """备用方法：手动生成文件的树结构"""
        extensions = self._get_current_extensions()
        
        # Docker环境：使用find命令获取文件列表
        return self._get_docker_find_structure(extensions)
    
    def read_file_content(self, file_path: str) -> str:
        """读取文件内容"""
        try:
            # 只支持Docker环境中读取文件
            return self._read_file_from_docker(file_path)
        except Exception as e:
            print(f"Warning: Could not read file {file_path}: {e}")
            return ""
    
    def _read_file_from_docker(self, file_path: str) -> str:
        """从Docker容器中读取文件内容"""
        try:
            # 构建容器中的文件路径，确保路径正确
            container_path = file_path.lstrip('/')
            
            # 使用cat命令读取文件
            result = self.docker_runner.run_command(f"cat '{container_path}'")
            
            if result.get("returncode") == 0:
                return result.get("stdout", "")
            else:
                print(f"Warning: Failed to read file from container {file_path}: {result.get('stderr', '')}")
                return ""
                
        except Exception as e:
            print(f"Warning: Exception reading file from Docker {file_path}: {e}")
            return ""
    
    def get_language_from_path(self, file_path: str) -> str:
        """根据文件路径确定语言"""
        if self.language != "auto":
            return self.language
        
        # 自动检测语言
        file_ext = Path(file_path).suffix.lower()
        for lang, extensions in self.language_extensions.items():
            if file_ext in extensions:
                return lang
        
        return "text"
    
    def find_special_files_info(self) -> str:
        """查找特殊文件及其导入信息（如Python的__init__.py、Java的package-info.java等）"""
        if self.language == "auto":
            return ""
        
        special_files = self.language_special_files.get(self.language, [])
        if not special_files:
            return ""
        
        special_info = []
        
        for special_file in special_files:
            # 在Docker环境中查找所有特殊文件
            found_files = self._find_files_in_docker(special_file)
            
            for relative_path in found_files:
                content = self.read_file_content(relative_path)
                
                # 提取import语句（根据语言调整）
                import_lines = self._extract_import_statements(content, self.language)
                
                if import_lines:
                    special_info.append(f"File: {relative_path}")
                    special_info.extend(import_lines)
                    special_info.append("")
        
        return "\n".join(special_info)
    
    def _find_files_in_docker(self, filename: str) -> List[str]:
        """在Docker容器中查找特定文件"""
        try:
            result = self.docker_runner.run_command(f"find . -name '{filename}' -type f")
            
            if result.get("returncode") == 0 and result.get("stdout"):
                # 清理路径，移除前导的./
                files = []
                for line in result["stdout"].split('\n'):
                    line = line.strip()
                    if line and line.startswith('./'):
                        clean_path = line[2:]  # 移除 './'
                        if clean_path:
                            files.append(clean_path)
                return files
            else:
                return []
                
        except Exception as e:
            print(f"Warning: Failed to find files in Docker: {e}")
            return []
    
    def _extract_import_statements(self, content: str, language: str) -> List[str]:
        """根据语言提取import语句"""
        import_lines = []
        
        for line in content.split('\n'):
            line = line.strip()
            
            if language == "python":
                if line.startswith('import ') or line.startswith('from '):
                    import_lines.append(line)
            elif language == "java":
                if line.startswith('import ') or line.startswith('package '):
                    import_lines.append(line)
            elif language in ["c#", "csharp"]:
                if line.startswith('using '):
                    import_lines.append(line)
            elif language in ["typescript", "javascript"]:
                if line.startswith('import ') or line.startswith('export ') or 'require(' in line:
                    import_lines.append(line)
            elif language == "go":
                if line.startswith('import ') or line.startswith('package '):
                    import_lines.append(line)
            elif language == "rust":
                if line.startswith('use ') or line.startswith('mod '):
                    import_lines.append(line)
        
        return import_lines
    
    def call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用LLM"""
        if not self.llm_client:
            raise ValueError("LLM client not provided")
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # 使用CopilotProxyLLMClient的query方法
        response = self.llm_client.query(messages)
        return response
    
    def parse_dependent_files(self, response: str) -> List[str]:
        try:
            pattern = r'```json\n(.*?)\n```'   
            match = re.search(pattern, response.strip(), re.DOTALL)  
            if match:   
                data = json.loads(match.group(1))
                return data.get("dependent_files", [])
            else:
                data = json.loads(response.strip())
                return data.get("dependent_files", [])
        except json.JSONDecodeError:
            print("Response is not valid JSON when parse_dependent_files")
            return []
    
    def parse_dependent_codes(self, response: str) -> str:
        try:
            pattern = r'```json\n(.*?)\n```'   
            match = re.search(pattern, response.strip(), re.DOTALL)  
            if match:   
                data = json.loads(match.group(1))
                return data.get("invoked_code_snippet", "")
            else:
                data = json.loads(response.strip())
                return data.get("invoked_code_snippet", "")
        except json.JSONDecodeError:
            print("Response is not valid JSON when parse_dependent_codes")
            return ""
    
    # def _clean_json_response(self, response: str) -> str:
    #     """清理LLM响应，提取有效的JSON"""
    #     # 移除markdown代码块标记
    #     if "```json" in response:
    #         json_start = response.find("```json") + 7
    #         json_end = response.find("```", json_start)
    #         if json_end != -1:
    #             response = response[json_start:json_end]
    #     elif "```" in response:
    #         # 处理没有json标记的代码块
    #         first_brace = response.find("{")
    #         if first_brace != -1:
    #             # 从第一个大括号开始查找
    #             brace_count = 0
    #             end_pos = first_brace
    #             for i, char in enumerate(response[first_brace:], first_brace):
    #                 if char == "{":
    #                     brace_count += 1
    #                 elif char == "}":
    #                     brace_count -= 1
    #                     if brace_count == 0:
    #                         end_pos = i + 1
    #                         break
    #             response = response[first_brace:end_pos]
        
    #     # 处理包含三重引号的字符串
    #     response = response.replace('"""', '"')
        
    #     # 移除前后空白
    #     return response.strip()
    
    def _file_exists_in_docker(self, file_path: str) -> bool:
        """检查文件在Docker容器中是否存在"""
        try:
            container_path = file_path.lstrip('/')
            result = self.docker_runner.run_command(f"test -f '{container_path}' && echo 'EXISTS' || echo 'NOT_FOUND'")
            return result.get("returncode") == 0 and "EXISTS" in result.get("stdout", "")
        except Exception:
            return False
    
    def find_dependent_files(self, target_file_path: str, target_file_content: str) -> List[str]:
        """查找依赖文件"""
        try:
            project_tree = self.get_project_tree_structure()
            language = self.get_language_from_path(target_file_path)
            
            user_prompt = SEARCH_DEPENDENT_FILES_USER_PROMPT.format(
                PROJECT_TREE_STRUCTURE=project_tree,
                TARGET_FILE_PATH=target_file_path,
                TARGET_FILE_CONTENT=target_file_content,
                LANGUAGE=language
            )
            
            # 添加特殊文件信息（如Python的__init__.py等）
            special_info = self.find_special_files_info()
            if special_info:
                user_prompt += "\n\n" + SEARCH_DEPENDENT_FILES_EXTRA_USER_PROMPT.format(
                    INIT_FILE_IMPORTS=special_info
                )
            
            llm_response = self.call_llm(SEARCH_DEPENDENT_FILES_SYSTEM_PROMPT, user_prompt)
            return self.parse_dependent_files(llm_response)
        
        except Exception as e:
            print(f"Error in find_dependent_files: {e}")
            return []
    
    def extract_dependent_codes(self, code_query: str, target_file_path: str, target_file_content: str) -> str:
        """从目标文件中提取相关代码"""
        try:
            language = self.get_language_from_path(target_file_path)
            
            user_prompt = SEARCH_DEPENDENT_CODES_USER_PROMPT.format(
                CODE_QUERY=code_query,
                TARGET_FILE_CONTENT=target_file_content,
                LANGUAGE=language
            )
            
            llm_response = self.call_llm(SEARCH_DEPENDENT_CODES_SYSTEM_PROMPT, user_prompt)
            return self.parse_dependent_codes(llm_response)
        
        except Exception as e:
            print(f"Error in extract_dependent_codes: {e}")
            return ""
    
    def search_related_codes(self, target_file_path: str, max_depth: int = 3) -> str:  
        """  
        搜索相关代码的主函数  
    
        Args:  
            target_file_path: 目标文件路径（相对于项目根目录）  
            max_depth: 最大搜索深度，防止无限递归  
    
        Returns:  
            str: 拼接后的所有相关代码  
        """  
        if not self.llm_client:  
            raise ValueError("LLM client is required for searching related codes")  
    
        # 记录已处理的文件，避免重复处理  
        processed_files: Set[str] = set()  
        # 存储所有找到的相关代码  
        all_related_codes: Dict[str, str] = {}  
        # 存储文件间的依赖关系  
        dependency_graph: Dict[str, List[str]] = {}  
    
        # 待处理的文件队列，BFS风格，每个元素为 (file_path, 当前深度)  
        files_to_process = [(target_file_path, 0)]  
    
        while files_to_process:  
            file_path, cur_depth = files_to_process.pop(0)  
            if file_path in processed_files:  
                continue  
            if cur_depth > max_depth:  
                continue  
            processed_files.add(file_path)  
    
            # 读取文件内容  
            file_content = self.read_file_content(file_path)  
            if not file_content:  
                continue  
    
            print(f"Processing file: {file_path} (depth: {cur_depth})")  
    
            # 如果是主文件，直接用全部内容  
            if file_path == target_file_path:  
                all_related_codes[file_path] = file_content  
                main_file_code = file_content  
            else:  
                main_file_code = all_related_codes.get(target_file_path, "")  
                related_code = self.extract_dependent_codes(  
                    main_file_code, file_path, file_content  
                )  
                if related_code and related_code.strip():  
                    all_related_codes[file_path] = related_code  
                else:  
                    print(f"No relevant code found in {file_path}")  
                    continue  
    
            # 查找当前文件的依赖文件  
            dependent_files = self.find_dependent_files(file_path, file_content)  
            if dependent_files:  
                dependency_graph[file_path] = dependent_files  
                print(f"Found dependencies for {file_path}: {dependent_files}")  
                # 新依赖文件入队，防止重复  
                for dep_file in dependent_files:  
                    if dep_file not in processed_files:  
                        # 检查文件是否存在  
                        if self._file_exists_in_docker(dep_file):  
                            files_to_process.append((dep_file, cur_depth + 1))  
                        else:  
                            print(f"Warning: Dependency file not found: {dep_file}")  
    
        if not all_related_codes:  
            return ""  
    
        # 根据依赖关系拼接代码，加深度限制  
        return self._assemble_codes_by_dependency(  
            all_related_codes, dependency_graph, target_file_path, max_depth  
        )  
    
    
    def _assemble_codes_by_dependency(self, all_codes: Dict[str, str],  
                                    dependency_graph: Dict[str, List[str]],  
                                    start_file: str, max_depth: int = 3) -> str:  
        """  
        根据依赖关系拼接代码，防止递归爆栈和循环依赖  
        """  
        assembled_code = []  
        visited = set()  
    
        def add_file_code(file_path: str, cur_depth: int):  
            if file_path in visited:  
                return  
            if cur_depth > max_depth:  
                return  
            if file_path not in all_codes:  
                return  
            visited.add(file_path)  
            # 先添加依赖文件的代码  
            if file_path in dependency_graph:  
                for dep_file in dependency_graph[file_path]:  
                    add_file_code(dep_file, cur_depth + 1)  
            # 然后加当前文件的代码  
            code = all_codes[file_path]  
            if code.strip():  
                assembled_code.append(f"# File: {file_path}")  
                assembled_code.append(code)  
                assembled_code.append("")  
    
        add_file_code(start_file, 0)  
        return "\n".join(assembled_code)  


def create_docker_related_code_searcher(project_root: str, language: str = "auto", 
                                       llm_client=None, container_name: str = None, 
                                       docker_image: str = None, testbed_path: str = "/testbed") -> RelatedCodeSearcher:
    """
    创建Docker环境的相关代码搜索器
    
    Args:
        project_root: 项目根目录路径
        language: 编程语言
        llm_client: LLM客户端
        container_name: Docker容器名称
        docker_image: Docker镜像名称
        testbed_path: 容器中的测试床路径
        
    Returns:
        RelatedCodeSearcher: 配置了Docker运行器的搜索器实例
    """
    docker_runner = DockerCommandRunner(
        container_name=container_name,
        docker_image=docker_image,
        testbed_path=testbed_path
    )
    
    return RelatedCodeSearcher(
        project_root=project_root,
        language=language,
        llm_client=llm_client,
        docker_runner=docker_runner
    )


# if __name__ == "__main__":
    # import argparse
    
    # # 使用示例
    # parser = argparse.ArgumentParser(description="Search related codes for a target file in Docker environment")
    # parser.add_argument("--project-root", default="/testbed", 
    #                    help="Project root directory in Docker container")
    # parser.add_argument("--target-file", default="tests/test_component_extra.py",
    #                    help="Target file to search dependencies for")
    # parser.add_argument("--language", default="python", 
    #                    choices=["python", "java", "c#", "typescript", "javascript", "auto"],
    #                    help="Programming language")
    # parser.add_argument("--max-depth", type=int, default=3,
    #                    help="Maximum search depth")
    
    # # Docker相关参数（必需）
    # parser.add_argument("--container", default="coverage_analyzer", 
    #                    help="Docker container name")
    # parser.add_argument("--image", 
    #                    default="codeexecservice.azurecr.io/pythontestgen.eval.x86_64.larq-zookeeper-v1:msbench-0.0.0",
    #                    help="Docker image name")
    # parser.add_argument("--testbed-path", default="/testbed",
    #                    help="Path to the testbed in the container")
    
    # args = parser.parse_args()
    
    # llm_client = CopilotProxyLLMClient()
    
    # print(f"\n=== 搜索 {args.language} 相关代码（Docker环境）===")
    # print(f"项目根目录: {args.project_root}")
    # print(f"目标文件: {args.target_file}")
    # print(f"容器名称: {args.container}")
    # print(f"镜像名称: {args.image}")
    
    # # 创建Docker环境的搜索器
    # searcher = create_docker_related_code_searcher(
    #     project_root=args.project_root,
    #     language=args.language,
    #     llm_client=llm_client,
    #     container_name=args.container,
    #     docker_image=args.image,
    #     testbed_path=args.testbed_path
    # )
    
    # result = searcher.search_related_codes(args.target_file, max_depth=args.max_depth)
    
    # if result:
    #     print("\n找到的相关代码：")
    #     print("=" * 50)
    #     print(result)
    # else:
    #     print("没有找到相关代码")
