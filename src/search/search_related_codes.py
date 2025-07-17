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
    """Main class for searching related code"""
    
    def __init__(self, project_root: str, language: str = "auto", llm_client=None, docker_runner: DockerCommandRunner = None):
        """
        Initialize the searcher
        
        Args:
            project_root: Project root directory path (path in Docker container)
            language: Programming language ("java", "python", "c#", "typescript", "auto")
            llm_client: LLM client, needs to implement query method
            docker_runner: Docker command runner, used to execute commands in container
        """
        self.project_root = Path(project_root).resolve()
        self.language = language.lower()
        self.llm_client = llm_client or (CopilotProxyLLMClient() if CopilotProxyLLMClient else None)
        self.docker_runner = docker_runner
        
        if not self.docker_runner:
            raise ValueError("Docker runner is required for this implementation")
        
        # Language to file extension mapping
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
        
        # Language to special file name mapping
        self.language_special_files = {
            "python": ["__init__.py"],
            "java": ["package-info.java"],
            "javascript": ["index.js"],
            "typescript": ["index.ts"],
            "c#": ["AssemblyInfo.cs"],
            "csharp": ["AssemblyInfo.cs"]
        }
        
    def get_project_tree_structure(self) -> str:
        """Get project tree structure, filter related files by language"""
        try:
            # Get file extensions for current language
            extensions = self._get_current_extensions()
            
            # Handle Docker environment
            return self._get_docker_tree_structure(extensions)
                
        except Exception as e:
            print(f"Warning: Failed to get tree structure: {e}")
            return self._generate_tree_structure_fallback()
    
    def _get_docker_tree_structure(self, extensions: List[str]) -> str:
        """Get project tree structure in Docker environment"""
        try:
            # First try to install tree command (if not exists)
            install_result = self.docker_runner.run_command("which tree || (apt-get update && apt-get install -y tree)")
            
            if extensions:
                # Build tree command pattern
                patterns = [f"*{ext}" for ext in extensions]
                pattern_str = " -o ".join([f"-P '{p}'" for p in patterns])
                command = f"tree {pattern_str} --prune"
            else:
                # If language not specified or auto, show all files
                command = "tree"
            
            result = self.docker_runner.run_command(command)
            
            if result.get("stdout") and result.get("returncode") == 0:
                return result["stdout"]
            else:
                # If tree command fails, use find command as fallback
                return self._get_docker_find_structure(extensions)
                
        except Exception as e:
            print(f"Warning: Docker tree command failed: {e}")
            return self._get_docker_find_structure(extensions)
    
    def _get_docker_find_structure(self, extensions: List[str]) -> str:
        """Use find command to get file structure in Docker"""
        try:
            if extensions:
                # Build find command file type filter
                name_patterns = [f"-name '*{ext}'" for ext in extensions]
                find_pattern = " -o ".join(name_patterns)
                command = f"find . -type f \\( {find_pattern} \\) | sort"
            else:
                # Show all files, but exclude common hidden directories
                command = "find . -type f -not -path './.git/*' -not -path './.*' | sort"
            
            result = self.docker_runner.run_command(command)
            
            if result.get("stdout") and result.get("returncode") == 0:
                # Convert find output to tree-like format
                return self._format_find_output_as_tree(result["stdout"])
            else:
                return self._generate_tree_structure_fallback()
                
        except Exception as e:
            print(f"Warning: Docker find command failed: {e}")
            return self._generate_tree_structure_fallback()
    
    
    def _format_find_output_as_tree(self, find_output: str) -> str:
        """Format find command output to tree-like structure"""
        lines = [line.strip() for line in find_output.split('\n') if line.strip()]
        if not lines:
            return ""
        
        # Build directory structure
        tree_lines = ["Project Structure:"]
        processed_paths = set()
        
        # Sort by path depth and alphabetical order
        lines.sort(key=lambda x: (x.count('/'), x))
        
        for line in lines:
            # Remove leading ./
            path = line.lstrip('./')
            if not path or path in processed_paths:
                continue
                
            processed_paths.add(path)
            parts = path.split('/')
            
            # Build tree structure display
            depth = len(parts) - 1
            indent = "  " * depth
            filename = parts[-1]
            
            if depth == 0:
                tree_lines.append(f"├── {filename}")
            else:
                tree_lines.append(f"{indent}├── {filename}")
        
        return '\n'.join(tree_lines)
    
    def _get_current_extensions(self) -> List[str]:
        """Get file extensions for current language"""
        if self.language == "auto":
            return []
        return self.language_extensions.get(self.language, [])
    
    def _generate_tree_structure_fallback(self) -> str:
        """Fallback method: manually generate file tree structure"""
        extensions = self._get_current_extensions()
        
        # Docker environment: use find command to get file list
        return self._get_docker_find_structure(extensions)
    
    def read_file_content(self, file_path: str) -> str:
        """Read file content"""
        try:
            # Only support reading files in Docker environment
            return self._read_file_from_docker(file_path)
        except Exception as e:
            print(f"Warning: Could not read file {file_path}: {e}")
            return ""
    
    def _read_file_from_docker(self, file_path: str) -> str:
        """Read file content from Docker container"""
        try:
            # Build file path in container, ensure path is correct
            container_path = file_path.lstrip('/')
            
            # Use cat command to read file
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
        """Determine language based on file path"""
        if self.language != "auto":
            return self.language
        
        # Auto detect language
        file_ext = Path(file_path).suffix.lower()
        for lang, extensions in self.language_extensions.items():
            if file_ext in extensions:
                return lang
        
        return "text"
    
    def find_special_files_info(self) -> str:
        """Find special files and their import info (like Python's __init__.py, Java's package-info.java, etc.)"""
        if self.language == "auto":
            return ""
        
        special_files = self.language_special_files.get(self.language, [])
        if not special_files:
            return ""
        
        special_info = []
        
        for special_file in special_files:
            # Find all special files in Docker environment
            found_files = self._find_files_in_docker(special_file)
            
            for relative_path in found_files:
                content = self.read_file_content(relative_path)
                
                # Extract import statements (adjust based on language)
                import_lines = self._extract_import_statements(content, self.language)
                
                if import_lines:
                    special_info.append(f"File: {relative_path}")
                    special_info.extend(import_lines)
                    special_info.append("")
        
        return "\n".join(special_info)
    
    def _find_files_in_docker(self, filename: str) -> List[str]:
        """Find specific files in Docker container"""
        try:
            result = self.docker_runner.run_command(f"find . -name '{filename}' -type f")
            
            if result.get("returncode") == 0 and result.get("stdout"):
                # Clean paths, remove leading ./
                files = []
                for line in result["stdout"].split('\n'):
                    line = line.strip()
                    if line and line.startswith('./'):
                        clean_path = line[2:]  # Remove './'
                        if clean_path:
                            files.append(clean_path)
                return files
            else:
                return []
                
        except Exception as e:
            print(f"Warning: Failed to find files in Docker: {e}")
            return []
    
    def _extract_import_statements(self, content: str, language: str) -> List[str]:
        """Extract import statements based on language"""
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
        """Call LLM"""
        if not self.llm_client:
            raise ValueError("LLM client not provided")
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        
        # Use CopilotProxyLLMClient's query method
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
    
    def _file_exists_in_docker(self, file_path: str) -> bool:
        """Check if file exists in Docker container"""
        try:
            container_path = file_path.lstrip('/')
            result = self.docker_runner.run_command(f"test -f '{container_path}' && echo 'EXISTS' || echo 'NOT_FOUND'")
            return result.get("returncode") == 0 and "EXISTS" in result.get("stdout", "")
        except Exception:
            return False
    
    def find_dependent_files(self, target_file_path: str, target_file_content: str) -> List[str]:
        """Find dependent files"""
        try:
            project_tree = self.get_project_tree_structure()
            language = self.get_language_from_path(target_file_path)
            
            user_prompt = SEARCH_DEPENDENT_FILES_USER_PROMPT.format(
                PROJECT_TREE_STRUCTURE=project_tree,
                TARGET_FILE_PATH=target_file_path,
                TARGET_FILE_CONTENT=target_file_content,
                LANGUAGE=language
            )
            
            # Add special file info (like Python's __init__.py, etc.)
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
        """Extract related code from target file"""
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
        Main function to search related codes  
    
        Args:  
            target_file_path: Target file path (relative to project root)  
            max_depth: Maximum search depth, prevent infinite recursion  
    
        Returns:  
            str: Concatenated all related codes  
        """  
        if not self.llm_client:  
            raise ValueError("LLM client is required for searching related codes")  
    
        # Record processed files, avoid duplicate processing  
        processed_files: Set[str] = set()  
        # Store all found related codes  
        all_related_codes: Dict[str, str] = {}  
        # Store dependencies between files  
        dependency_graph: Dict[str, List[str]] = {}  
    
        # Queue of files to process, BFS style, each element is (file_path, current_depth)  
        files_to_process = [(target_file_path, 0)]  
    
        while files_to_process:  
            file_path, cur_depth = files_to_process.pop(0)  
            if file_path in processed_files:  
                continue  
            if cur_depth > max_depth:  
                continue  
            processed_files.add(file_path)  
    
            # Read file content  
            file_content = self.read_file_content(file_path)  
            if not file_content:  
                continue  
    
            print(f"Processing file: {file_path} (depth: {cur_depth})")  
    
            # If it's the main file, use full content directly  
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
    
            # Find dependent files of current file  
            dependent_files = self.find_dependent_files(file_path, file_content)  
            if dependent_files:  
                dependency_graph[file_path] = dependent_files  
                print(f"Found dependencies for {file_path}: {dependent_files}")  
                # Enqueue new dependency files, prevent duplicates  
                for dep_file in dependent_files:  
                    if dep_file not in processed_files:  
                        # Check if file exists  
                        if self._file_exists_in_docker(dep_file):  
                            files_to_process.append((dep_file, cur_depth + 1))  
                        else:  
                            print(f"Warning: Dependency file not found: {dep_file}")  
    
        if not all_related_codes:  
            return ""  
    
        # Assemble codes based on dependency relationships, with depth limit  
        return self._assemble_codes_by_dependency(  
            all_related_codes, dependency_graph, target_file_path, max_depth  
        )  
    
    
    def _assemble_codes_by_dependency(self, all_codes: Dict[str, str],  
                                    dependency_graph: Dict[str, List[str]],  
                                    start_file: str, max_depth: int = 3) -> str:  
        """  
        Assemble codes based on dependency relationships, prevent stack overflow and circular dependencies  
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
            # First add dependent files' code  
            if file_path in dependency_graph:  
                for dep_file in dependency_graph[file_path]:  
                    add_file_code(dep_file, cur_depth + 1)  
            # Then add current file's code  
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
    Create related code searcher for Docker environment
    
    Args:
        project_root: Project root directory path
        language: Programming language
        llm_client: LLM client
        container_name: Docker container name
        docker_image: Docker image name
        testbed_path: Testbed path in container
        
    Returns:
        RelatedCodeSearcher: Searcher instance configured with Docker runner
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
    
    # parser.add_argument("--container", default="coverage_analyzer", 
    #                    help="Docker container name")
    # parser.add_argument("--image", 
    #                    default="codeexecservice.azurecr.io/pythontestgen.eval.x86_64.larq-zookeeper-v1:msbench-0.0.0",
    #                    help="Docker image name")
    # parser.add_argument("--testbed-path", default="/testbed",
    #                    help="Path to the testbed in the container")
    
    # args = parser.parse_args()
    
    # llm_client = CopilotProxyLLMClient()
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
    #     print("=" * 50)
    #     print(result)
    # else:
    #     print("No related codes found.")
