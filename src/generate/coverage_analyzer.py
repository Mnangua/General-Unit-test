import os
import json
import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, List, Set, Tuple, Optional, Any
from pathlib import Path
from dataclasses import dataclass
from enum import Enum

from src.utils import run_custom_command, DockerCommandRunner


class CoverageType(Enum):
    LINE = "line"
    BRANCH = "branch"



@dataclass
class UncoveredCode:
    file_path: str
    line_start: int
    line_end: int
    code_snippet: str
    coverage_type: CoverageType
    function_name: Optional[str] = None
    branch_condition: Optional[str] = None
    

@dataclass
class CoverageReport:
    language: str
    uncovered_lines: List[Any]
    coverage_percentage: float
    tests_output: str = ""  # 测试输出结果，可能包含测试失败信息等
    

class CoverageAnalyzer:
    """覆盖率分析器基类"""
    
    def __init__(self, project_root: str, language: str, docker_runner: DockerCommandRunner = None):
        self.project_root = Path(project_root).resolve()
        self.language = language.lower()
        self.docker_runner = docker_runner
        
    def collect_coverage(self) -> CoverageReport:
        """收集覆盖率数据"""
        raise NotImplementedError
        
    def find_uncovered_code(self) -> List[UncoveredCode]:
        """查找未覆盖的代码"""
        raise NotImplementedError
    
    def _run_command(self, command: str, work_dir: str = None) -> Dict[str, str]:
        """运行命令，支持Docker和本地执行"""
        if self.docker_runner:
            return self.docker_runner.run_command(command, work_dir)
        else:
            # 本地执行
            return run_custom_command(
                work_dir=work_dir or str(self.project_root),
                command=command
            )


class PythonCoverageAnalyzer(CoverageAnalyzer):
    """Python coverage.py 分析器"""
    
    def __init__(self, project_root: str, test_command: str = "python -m pytest", 
                 source_dirs: List[str] = None, docker_runner: DockerCommandRunner = None):
        super().__init__(project_root, "python", docker_runner)
        self.test_command = test_command
        self.coverage_file = self.project_root / ".coverage"
        self.source_dirs = source_dirs or ["."]
        self.python_cmd = "python"  # Default, will be detected during installation
        
        
    def collect_coverage(self) -> CoverageReport:
        try:
            if not self._activate_conda_env():
                print("⚠️ Failed to activate Conda environment, coverage collection may not work properly.")
                return self._create_empty_report()
            
            # 运行测试并收集覆盖率
            print("Running tests with coverage...")
            env_cmds = [  
                'export AGENT_DIR="/agent"',  
                'export TESTBED_DIR="/testbed"',  
                'export OUTPUT_DIR="/output"',  
                'export METADATA_PATH="/metadata.json"',  
                'export EVAL_SCRIPT_PATH="/eval.sh"'  
            ]  
            cmd = " && ".join(env_cmds + ['python3 /eval/all_test_coverage_eval.py'])  
            result = self._run_command(cmd)  
            if result.get("returncode") != 0:  
                print(f"✗ 外部评估脚本执行失败:\n{result.get('stderr')}") 
            
            return self._parse_coverage_report()
            
        except Exception as e:
            print(f"Error collecting Python coverage: {e}")
            return self._create_empty_report()
    
    def _create_empty_report(self) -> CoverageReport:
        return CoverageReport("python", [], 0.0, "")
    
    def _parse_coverage_report(self) -> CoverageReport:
        if self.docker_runner:
            self._copy_coverage_files_from_docker()
        
        coverage_json_path = self.project_root / "coverage.json"
        coverage_xml_path = self.project_root / "coverage.xml"
        uncovered_code_json_path = self.project_root / "uncovered_code.json"
                        
        # 解析XML并生成UncoveredCode对象（保留原有逻辑以防备用）
        uncovered_code_objects = self._parse_xml_coverage(coverage_xml_path)
        
        # 尝试从uncovered_code.json加载数据并转换为与该文件相同的格式
        uncovered_lines = []
        if uncovered_code_json_path.exists():
            try:
                with open(uncovered_code_json_path, 'r', encoding='utf-8') as f:
                    uncovered_data = json.load(f)
                    uncovered_lines = uncovered_data  # 直接使用json中的格式
                print(f"✓ Loaded uncovered code data from uncovered_code.json: {len(uncovered_lines)} files")
            except Exception as e:
                print(f"⚠ Failed to load uncovered_code.json: {e}")
                # 如果加载失败，回退到UncoveredCode对象
                uncovered_lines = uncovered_code_objects
        else:
            print("⚠ uncovered_code.json not found, using parsed XML data")
            uncovered_lines = uncovered_code_objects
        
        coverage_percentage = 0.0
        if coverage_json_path.exists():
            try:
                with open(coverage_json_path, 'r', encoding='utf-8') as f:
                    coverage_data = json.load(f)
                    coverage_percentage = coverage_data.get("coverage_LINE", 0.0)
                    tests_output = coverage_data.get("tests_output", "")
            except Exception as e:
                print(f"⚠ Failed to load coverage.json: {e}")
        
        return CoverageReport(
            language="python",
            uncovered_lines=uncovered_lines,
            coverage_percentage=coverage_percentage,
            tests_output=tests_output if 'tests_output' in locals() else ""
        )
    
    def _copy_coverage_files_from_docker(self):
        if not self.docker_runner or not self.docker_runner.container_name:
            return
        
        # Ensure the local output directory exists
        os.makedirs(self.project_root, exist_ok=True)
        
        files_to_copy = [
            ("/output/eval.json", "coverage.json"),
            ("/testbed/coverage.xml", "coverage.xml"),
            ("/testbed/uncovered_code.json", "uncovered_code.json"),
        ]
        
        for container_file, local_file in files_to_copy:
            container_path = container_file
            local_path = str(self.project_root / local_file)
            
            # First check if the file exists in the container
            check_result = self.docker_runner.run_command(f"test -f {container_file} && echo 'EXISTS' || echo 'NOT_FOUND'")
            if "EXISTS" not in check_result.get("stdout", ""):
                print(f"⚠ {container_file} not found in Docker container")
                continue
            
            success = self.docker_runner.copy_file_from_container(container_path, local_path)
            if success:
                print(f"✓ Copied {container_file} from Docker container")
                # Verify the file was copied and has content
                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    print(f"✓ {local_file} successfully copied and has content")
                else:
                    print(f"⚠ {local_file} copied but appears empty or corrupted")
            else:
                print(f"⚠ Failed to copy {container_file} from Docker container")
    
    def _parse_xml_coverage(self, xml_path: Path) -> List[UncoveredCode]:
        """解析XML覆盖率报告找到未覆盖的代码 - 在Docker内部执行解析"""
        uncovered_code = []
        
        if self.docker_runner:
            # 在Docker内部执行XML解析
            return self._parse_xml_coverage_in_docker()
        else:
            # 本地解析（保留原始逻辑作为fallback）
            return self._parse_xml_coverage_local(xml_path)
    
    def _parse_xml_coverage_in_docker(self) -> List[UncoveredCode]:
        """在Docker容器内部执行XML覆盖率解析"""
        uncovered_code = []
        
        try:
            # 1. 复制XML解析脚本到Docker容器的/eval目录
            parser_script_path = Path(__file__).parent / "xml_coverage_parser.py"
            if not parser_script_path.exists():
                print(f"⚠ XML parser script not found: {parser_script_path}")
                return uncovered_code
            
            # 读取解析脚本内容
            with open(parser_script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            
            # 将脚本内容写入容器中的临时文件
            # 使用base64编码来避免特殊字符和heredoc问题
            import base64
            script_content_b64 = base64.b64encode(script_content.encode('utf-8')).decode('ascii')
            script_copy_cmd = f"echo '{script_content_b64}' | base64 -d > /eval/xml_coverage_parser.py"
            
            copy_result = self.docker_runner.run_command(script_copy_cmd)
            if copy_result.get("returncode") != 0:
                print(f"⚠ Failed to copy XML parser script to container: {copy_result.get('stderr')}")
                return uncovered_code
            
            print("✓ XML parser script copied to Docker container")
            
            # 2. 在Docker内部执行XML解析
            xml_file_path = "/testbed/coverage.xml"  # XML文件在容器内的路径
            parse_cmd = f"cd /eval && python3 xml_coverage_parser.py {xml_file_path} /testbed"
            
            parse_result = self.docker_runner.run_command(parse_cmd)
            if parse_result.get("returncode") != 0:
                print(f"⚠ Failed to parse XML coverage in container: {parse_result.get('stderr')}")
                return uncovered_code
            
            # 3. 解析返回的JSON结果
            try:
                result_json = json.loads(parse_result.get("stdout", "{}"))
                
                if not result_json.get("success", False):
                    print(f"⚠ XML parsing failed: {result_json.get('error', 'Unknown error')}")
                    return uncovered_code
                
                # 转换JSON结果为UncoveredCode对象
                for uncovered_info in result_json.get("uncovered_code", []):
                    coverage_type = CoverageType.BRANCH if uncovered_info.get("coverage_type") == "branch" else CoverageType.LINE
                    
                    uncovered_code.append(UncoveredCode(
                        file_path=uncovered_info.get("file_path", ""),
                        line_start=uncovered_info.get("line_start", 0),
                        line_end=uncovered_info.get("line_end", 0),
                        code_snippet=uncovered_info.get("code_snippet", ""),
                        coverage_type=coverage_type,
                        function_name=uncovered_info.get("function_name"),
                        branch_condition=None  # 可以在后续版本中添加分支条件解析
                    ))
                
                print(f"✓ Successfully parsed {len(uncovered_code)} uncovered code segments from Docker")
                
                # 4. 生成uncovered_code.json文件
                self._generate_and_copy_uncovered_json(uncovered_code)
                
            except json.JSONDecodeError as e:
                print(f"⚠ Failed to parse JSON result from Docker: {e}")
                print(f"Raw output: {parse_result.get('stdout', '')[:500]}...")
                return uncovered_code
                
        except Exception as e:
            print(f"⚠ Error in Docker XML parsing: {e}")
        
        return uncovered_code
    
    def _generate_and_copy_uncovered_json(self, uncovered_code: List[UncoveredCode]):
        """生成uncovered_code.json文件并从Docker容器复制到本地"""
        try:
            # 1. 按文件路径分组未覆盖的代码
            file_uncovered_map = {}
            for uc in uncovered_code:
                file_path = uc.file_path
                if file_path not in file_uncovered_map:
                    file_uncovered_map[file_path] = []
                
                # 收集该文件的所有未覆盖行号
                uncovered_lines = list(range(uc.line_start, uc.line_end + 1))
                file_uncovered_map[file_path].extend(uncovered_lines)
            
            # 2. 在Docker容器中生成Python脚本来读取完整文件内容和合并未覆盖行号
            script_content = '''
import json
import os

file_uncovered_map = ''' + str(file_uncovered_map) + '''

uncovered_data = []
for file_path, uncovered_lines in file_uncovered_map.items():
    try:
        # 去重并排序未覆盖的行号
        unique_uncovered_lines = sorted(list(set(uncovered_lines)))
        
        # 读取完整文件内容
        full_file_path = os.path.join("/testbed", file_path.lstrip("/"))
        if os.path.exists(full_file_path):
            with open(full_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                full_code = f.read()
        else:
            # 如果文件不存在，尝试直接使用原路径
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    full_code = f.read()
            else:
                full_code = "# File not found: " + file_path
                
        uncovered_data.append({
            "file_path": file_path,
            "code": full_code,
            "uncovered_lines": unique_uncovered_lines
        })
        
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        uncovered_data.append({
            "file_path": file_path,
            "code": f"# Error reading file: {str(e)}",
            "uncovered_lines": sorted(list(set(uncovered_lines)))
        })

# 写入JSON文件
with open("/testbed/uncovered_code.json", "w", encoding="utf-8") as f:
    json.dump(uncovered_data, f, indent=2, ensure_ascii=False)

print(f"Generated uncovered_code.json with {len(uncovered_data)} files")
'''
            
            # 使用base64编码安全传输脚本内容到Docker容器
            import base64
            script_content_b64 = base64.b64encode(script_content.encode('utf-8')).decode('ascii')
            
            # 在容器中创建并执行Python脚本
            create_script_cmd = f"echo '{script_content_b64}' | base64 -d > /tmp/generate_uncovered.py"
            create_result = self.docker_runner.run_command(create_script_cmd)
            if create_result.get("returncode") != 0:
                print(f"⚠ Failed to create script in container: {create_result.get('stderr')}")
                return
            
            # 执行脚本生成uncovered_code.json
            exec_script_cmd = "cd /testbed && python3 /tmp/generate_uncovered.py"
            exec_result = self.docker_runner.run_command(exec_script_cmd)
            if exec_result.get("returncode") != 0:
                print(f"⚠ Failed to execute script in container: {exec_result.get('stderr')}")
                return
            
            print("✓ Generated uncovered_code.json in Docker container")
            
            # 3. 从Docker容器复制文件到本地
            container_path = "/testbed/uncovered_code.json"
            local_path = str(self.project_root / "uncovered_code.json")
            
            # 检查文件是否存在
            check_result = self.docker_runner.run_command(f"test -f {container_path} && echo 'EXISTS' || echo 'NOT_FOUND'")
            if "EXISTS" not in check_result.get("stdout", ""):
                print(f"⚠ {container_path} not found in Docker container")
                return
            
            # 复制文件
            success = self.docker_runner.copy_file_from_container(container_path, local_path)
            if success:
                print(f"✓ Copied {container_path} from Docker container")
                # 验证文件是否成功复制且有内容
                if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    print(f"✓ uncovered_code.json successfully copied and has content")
                    print(f"✓ Generated uncovered code data for {len(file_uncovered_map)} files")
                else:
                    print(f"⚠ uncovered_code.json copied but appears empty or corrupted")
            else:
                print(f"⚠ Failed to copy {container_path} from Docker container")
                
        except Exception as e:
            print(f"⚠ Error generating uncovered_code.json: {e}")

    def _parse_xml_coverage_local(self, xml_path: Path) -> List[UncoveredCode]:
        """本地解析XML覆盖率报告（原始实现，作为fallback）"""
        uncovered_code = []
        
        if not xml_path.exists():
            print(f"Coverage XML file not found: {xml_path}")
            return uncovered_code
        
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
            
            for package in root.findall('.//package'):
                for class_elem in package.findall('classes/class'):
                    filename = class_elem.get('filename', '')

                    print(f"Processing file: {filename}")
                    
                    # 只处理Python文件
                    if not filename.endswith('.py'):
                        continue
                    
                    for line in class_elem.findall('lines/line'):
                        hits = int(line.get('hits', '0'))
                        line_number = int(line.get('number', '0'))
                        
                        if hits == 0:  # 未覆盖的行
                            code_snippet = self._get_code_snippet_local(filename, line_number)
                            if code_snippet and code_snippet.strip():  # 忽略空行
                                # 检查是否是有意义的代码行（不是注释或空行）
                                stripped_code = code_snippet.strip()
                                if (not stripped_code.startswith('#') and 
                                    stripped_code not in ['', 'pass', '...'] and
                                    not stripped_code.startswith('"""') and
                                    not stripped_code.startswith("'''")):
                                    
                                    uncovered_code.append(UncoveredCode(
                                        file_path=filename,
                                        line_start=line_number,
                                        line_end=line_number,
                                        code_snippet=code_snippet,
                                        coverage_type=CoverageType.LINE
                                    ))
            
        except Exception as e:
            print(f"Error parsing XML coverage: {e}")
        
        return uncovered_code
    
    def _get_code_snippet_local(self, file_path: str, line_number: int) -> str:
        """获取指定行的代码片段（本地版本）"""
        try:
            # 在本地环境中，尝试直接访问文件
            full_path = self.project_root / file_path
            if not full_path.exists():
                # 尝试其他可能的路径
                full_path = Path(file_path)
                if not full_path.exists():
                    return ""
            
            with open(full_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if 1 <= line_number <= len(lines):
                    return lines[line_number - 1].rstrip()
        except Exception as e:
            print(f"Error reading code snippet from {file_path}:{line_number}: {e}")
        return ""
    
    def _activate_conda_env(self):
        print("--- Activating Conda Environment ---")
        
        # Check if conda is available
        conda_check = self._run_command("which conda")
        if conda_check.get("returncode") != 0:
            print("Conda not found, checking for miniconda...")
            conda_check = self._run_command("which /opt/miniconda3/bin/conda")
            if conda_check.get("returncode") != 0:
                print("⚠ Conda/Miniconda not available")
                return False
            conda_cmd = "/opt/miniconda3/bin/conda"
        else:
            conda_cmd = "conda"
        
        # Check if ces-env environment exists
        env_check = self._run_command(f"{conda_cmd} env list | grep ces-env")
        if env_check.get("returncode") != 0:
            print("⚠ ces-env environment not found")
            # List available environments for debugging
            env_list = self._run_command(f"{conda_cmd} env list")
            print(f"Available environments:\n{env_list.get('stdout', '')}")
            return False
        
        # Try to activate ces-env environment
        print("Activating ces-env environment...")
        activation_check = self._run_command("source /opt/miniconda3/bin/activate ces-env && echo 'Environment activated'")
        if activation_check.get("returncode") == 0 and "Environment activated" in activation_check.get("stdout", ""):
            print("✓ ces-env environment activated successfully")
            # Update command wrapper to always use activated environment
            self._conda_env_activated = True
            return True
        else:
            print(f"⚠ Failed to activate ces-env environment: {activation_check.get('stderr', '')}")
            return False

  
def create_docker_coverage_analyzer(container_name: str = None,  
                                    docker_image: str = None,  
                                    testbed_path: str = "/testbed",  
                                    output_dir: str = "./docker_output/related_code_exp",  
                                    **kwargs) -> CoverageAnalyzer:  
    docker_runner = DockerCommandRunner(container_name=container_name,  
                                        docker_image=docker_image,  
                                        testbed_path=testbed_path)  
    output_dir = Path(output_dir).resolve()  
    output_dir.mkdir(exist_ok=True)  
    return PythonCoverageAnalyzer(project_root=str(output_dir),  
                                    docker_runner=docker_runner,  
                                    **kwargs)  
  

# if __name__ == "__main__":
#     import argparse
#     # docker run -d --name coverage_analyzer codeexecservice.azurecr.io/pythontestgen.eval.x86_64.larq-zookeeper-v1:msbench-0.0.0  
#     # python /home/mengnanqi/General-Unit-Test/src/generate/coverage_analyzer.py --mode docker --container coverage_analyzer 
#     parser = argparse.ArgumentParser(description="Coverage analyzer with Docker support")
#     parser.add_argument("--mode", choices=["local", "docker"], default="docker", 
#                        help="Analysis mode: local or docker")
#     parser.add_argument("--container", help="Docker container name (for docker mode)")
#     parser.add_argument("--image", 
#                        default="codeexecservice.azurecr.io/pythontestgen.eval.x86_64.larq-zookeeper-v1:msbench-0.0.0",
#                        help="Docker image name")
    
#     args = parser.parse_args()
     
#     print(f"Container: {args.container or 'New container from image'}")
#     print(f"Image: {args.image}")
    
#     analyzer = create_docker_coverage_analyzer(
#         container_name=args.container,
#         docker_image=args.image if not args.container else None,
#     )
    
#     report = analyzer.collect_coverage()
    
#     print(f"\n=== Coverage Report ===")
#     print(f"Language: {report.language}")
#     print(f"Coverage: {report.coverage_percentage:.2f}%")
#     print(f"Uncovered data: {len(report.uncovered_lines)}")
    
    # if report.uncovered_lines:
    #     print(f"\n=== First 10 Uncovered Code Segments ===")
    #     for i, uncovered in enumerate(report.uncovered_lines[:10]):
    #         # dict - file_path, code, uncovered_lines
    #         file_path = uncovered.get("file_path", "")
    #         code = uncovered.get("code", "")
    #         uncovered_lines = uncovered.get("uncovered_lines", [])
    #         print(f"{i+1}. {file_path} - {len(uncovered_lines)} code: {code} uncovered lines: {uncovered_lines[:5]}{'...' if len(uncovered_lines) > 5 else ''}")



