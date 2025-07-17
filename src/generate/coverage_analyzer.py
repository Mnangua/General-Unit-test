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
    tests_output: str = ""  # Test output results, may contain test failure information, etc.
    

class CoverageAnalyzer:
    """Coverage analyzer base class"""
    
    def __init__(self, project_root: str, language: str, docker_runner: DockerCommandRunner = None):
        self.project_root = Path(project_root).resolve()
        self.language = language.lower()
        self.docker_runner = docker_runner
        
    def collect_coverage(self) -> CoverageReport:
        """Collect coverage data"""
        raise NotImplementedError
        
    def find_uncovered_code(self) -> List[UncoveredCode]:
        """Find uncovered code"""
        raise NotImplementedError
    
    def _run_command(self, command: str, work_dir: str = None) -> Dict[str, str]:
        """Run command, support Docker and local execution"""
        if self.docker_runner:
            return self.docker_runner.run_command(command, work_dir)
        else:
            # Local execution
            return run_custom_command(
                work_dir=work_dir or str(self.project_root),
                command=command
            )


class PythonCoverageAnalyzer(CoverageAnalyzer):
    """Python coverage.py analyzer"""
    
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
            
            # Run tests and collect coverage
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
                print(f"✗ External evaluation script execution failed:\n{result.get('stderr')}") 
            
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
                        
        # Parse XML and generate UncoveredCode objects (retain original logic for backup)
        uncovered_code_objects = self._parse_xml_coverage(coverage_xml_path)
        
        # Try to load data from uncovered_code.json and convert to same format as this file
        uncovered_lines = []
        if uncovered_code_json_path.exists():
            try:
                with open(uncovered_code_json_path, 'r', encoding='utf-8') as f:
                    uncovered_data = json.load(f)
                    uncovered_lines = uncovered_data  # Directly use format from json
                print(f"✓ Loaded uncovered code data from uncovered_code.json: {len(uncovered_lines)} files")
            except Exception as e:
                print(f"⚠ Failed to load uncovered_code.json: {e}")
                # If loading fails, fallback to UncoveredCode objects
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
        """Parse XML coverage report to find uncovered code - execute parsing inside Docker"""
        uncovered_code = []
        
        if self.docker_runner:
            # Execute XML parsing inside Docker
            return self._parse_xml_coverage_in_docker()
        else:
            # Local parsing (retain original logic as fallback)
            return self._parse_xml_coverage_local(xml_path)
    
    def _parse_xml_coverage_in_docker(self) -> List[UncoveredCode]:
        """Execute XML coverage parsing inside Docker container"""
        uncovered_code = []
        
        try:
            # 1. Copy XML parsing script to Docker container's /eval directory
            parser_script_path = Path(__file__).parent / "xml_coverage_parser.py"
            if not parser_script_path.exists():
                print(f"⚠ XML parser script not found: {parser_script_path}")
                return uncovered_code
            
            # Read parsing script content
            with open(parser_script_path, 'r', encoding='utf-8') as f:
                script_content = f.read()
            
            # Write script content to temporary file in container
            # Use base64 encoding to avoid special characters and heredoc issues
            import base64
            script_content_b64 = base64.b64encode(script_content.encode('utf-8')).decode('ascii')
            script_copy_cmd = f"echo '{script_content_b64}' | base64 -d > /eval/xml_coverage_parser.py"
            
            copy_result = self.docker_runner.run_command(script_copy_cmd)
            if copy_result.get("returncode") != 0:
                print(f"⚠ Failed to copy XML parser script to container: {copy_result.get('stderr')}")
                return uncovered_code
            
            print("✓ XML parser script copied to Docker container")
            
            # 2. Execute XML parsing inside Docker
            xml_file_path = "/testbed/coverage.xml"  # XML file path inside container
            parse_cmd = f"cd /eval && python3 xml_coverage_parser.py {xml_file_path} /testbed"
            
            parse_result = self.docker_runner.run_command(parse_cmd)
            if parse_result.get("returncode") != 0:
                print(f"⚠ Failed to parse XML coverage in container: {parse_result.get('stderr')}")
                return uncovered_code
            
            # 3. Parse returned JSON results
            try:
                result_json = json.loads(parse_result.get("stdout", "{}"))
                
                if not result_json.get("success", False):
                    print(f"⚠ XML parsing failed: {result_json.get('error', 'Unknown error')}")
                    return uncovered_code
                
                # Convert JSON results to UncoveredCode objects
                for uncovered_info in result_json.get("uncovered_code", []):
                    coverage_type = CoverageType.BRANCH if uncovered_info.get("coverage_type") == "branch" else CoverageType.LINE
                    
                    uncovered_code.append(UncoveredCode(
                        file_path=uncovered_info.get("file_path", ""),
                        line_start=uncovered_info.get("line_start", 0),
                        line_end=uncovered_info.get("line_end", 0),
                        code_snippet=uncovered_info.get("code_snippet", ""),
                        coverage_type=coverage_type,
                        function_name=uncovered_info.get("function_name"),
                        branch_condition=None  # Can add branch condition parsing in future versions
                    ))
                
                print(f"✓ Successfully parsed {len(uncovered_code)} uncovered code segments from Docker")
                
                # 4. Generate uncovered_code.json file
                self._generate_and_copy_uncovered_json(uncovered_code)
                
            except json.JSONDecodeError as e:
                print(f"⚠ Failed to parse JSON result from Docker: {e}")
                print(f"Raw output: {parse_result.get('stdout', '')[:500]}...")
                return uncovered_code
                
        except Exception as e:
            print(f"⚠ Error in Docker XML parsing: {e}")
        
        return uncovered_code
    
    def _generate_and_copy_uncovered_json(self, uncovered_code: List[UncoveredCode]):
        """Generate uncovered_code.json file and copy from Docker container to local"""
        try:
            # 1. Group uncovered code by file path
            file_uncovered_map = {}
            for uc in uncovered_code:
                file_path = uc.file_path
                if file_path not in file_uncovered_map:
                    file_uncovered_map[file_path] = []
                
                # Collect all uncovered line numbers for this file
                uncovered_lines = list(range(uc.line_start, uc.line_end + 1))
                file_uncovered_map[file_path].extend(uncovered_lines)
            
            # 2. Generate Python script in Docker container to read complete file content and merge uncovered line numbers
            script_content = '''
import json
import os

file_uncovered_map = ''' + str(file_uncovered_map) + '''

uncovered_data = []
for file_path, uncovered_lines in file_uncovered_map.items():
    try:
        # Remove duplicates and sort uncovered line numbers
        unique_uncovered_lines = sorted(list(set(uncovered_lines)))
        
        # Read complete file content
        full_file_path = os.path.join("/testbed", file_path.lstrip("/"))
        if os.path.exists(full_file_path):
            with open(full_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                full_code = f.read()
        else:
            # If file doesn't exist, try using original path directly
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

# Write JSON file
with open("/testbed/uncovered_code.json", "w", encoding="utf-8") as f:
    json.dump(uncovered_data, f, indent=2, ensure_ascii=False)

print(f"Generated uncovered_code.json with {len(uncovered_data)} files")
'''
            
            # Use base64 encoding to safely transfer script content to Docker container
            import base64
            script_content_b64 = base64.b64encode(script_content.encode('utf-8')).decode('ascii')
            
            # Create and execute Python script in container
            create_script_cmd = f"echo '{script_content_b64}' | base64 -d > /tmp/generate_uncovered.py"
            create_result = self.docker_runner.run_command(create_script_cmd)
            if create_result.get("returncode") != 0:
                print(f"⚠ Failed to create script in container: {create_result.get('stderr')}")
                return
            
            # Execute script to generate uncovered_code.json
            exec_script_cmd = "cd /testbed && python3 /tmp/generate_uncovered.py"
            exec_result = self.docker_runner.run_command(exec_script_cmd)
            if exec_result.get("returncode") != 0:
                print(f"⚠ Failed to execute script in container: {exec_result.get('stderr')}")
                return
            
            print("✓ Generated uncovered_code.json in Docker container")
            
            # 3. Copy file from Docker container to local
            container_path = "/testbed/uncovered_code.json"
            local_path = str(self.project_root / "uncovered_code.json")
            
            # Check if file exists
            check_result = self.docker_runner.run_command(f"test -f {container_path} && echo 'EXISTS' || echo 'NOT_FOUND'")
            if "EXISTS" not in check_result.get("stdout", ""):
                print(f"⚠ {container_path} not found in Docker container")
                return
            
            # Copy file
            success = self.docker_runner.copy_file_from_container(container_path, local_path)
            if success:
                print(f"✓ Copied {container_path} from Docker container")
                # Verify file was successfully copied and has content
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
        """Local parsing of XML coverage report (original implementation, as fallback)"""
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
                    
                    # Only process Python files
                    if not filename.endswith('.py'):
                        continue
                    
                    for line in class_elem.findall('lines/line'):
                        hits = int(line.get('hits', '0'))
                        line_number = int(line.get('number', '0'))
                        
                        if hits == 0:  # Uncovered lines
                            code_snippet = self._get_code_snippet_local(filename, line_number)
                            if code_snippet and code_snippet.strip():  # Ignore empty lines
                                # Check if it's meaningful code line (not comment or empty line)
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
        """Get code snippet for specified line (local version)"""
        try:
            # In local environment, try to access file directly
            full_path = self.project_root / file_path
            if not full_path.exists():
                # Try other possible paths
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



