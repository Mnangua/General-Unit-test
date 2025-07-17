#!/usr/bin/env python3
import os
import json
import re
import subprocess
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass

from src.generate.coverage_analyzer import create_docker_coverage_analyzer
from src.capi_client import CopilotProxyLLMClient
from src.utils import DockerCommandRunner
from src.postprocess.prompts import (
    ERROR_ANALYSIS_SYSTEM_PROMPT,
    ERROR_ANALYSIS_USER_PROMPT,
    UNIT_TESTS_FIX_V2_SYSTEM_PROMPT,
    UNIT_TESTS_FIX_V2_USER_PROMPT
)


@dataclass
class ErrorInfo:
    file_path: str
    line_range: List[int]  # [start_line, end_line]
    message: str


@dataclass
class FixResultV2:
    file_path: str
    original_code: str
    fix_type: str  # "code", "command", "unfixable"
    fixed_code: Optional[str] = None
    language: Optional[str] = None
    commands: Optional[List[str]] = None
    description: Optional[str] = None
    reason: Optional[str] = None
    success: bool = False
    error_message: Optional[str] = None


class CoverageBasedErrorFixerV2:
    def __init__(self, container_name: str, images: str, language: str, temp_dir: str, 
                 llm_client=None, max_fix_iterations: int = 3):
        self.language = language.lower()
        self.llm_client = llm_client
        self.container = container_name
        self.image = images
        self.temp_dir = temp_dir
        self.max_fix_iterations = max_fix_iterations
        
        self.coverage_analyzer = create_docker_coverage_analyzer(
            container_name=self.container,
            docker_image=self.image,
            output_dir=self.temp_dir,
        )
        self.docker_runner = DockerCommandRunner(
            container_name=self.container,
            docker_image=self.image,
            testbed_path="/testbed"
        )
    
    def fix_errors_and_collect_coverage(self) -> tuple[List[FixResultV2], Any, List[Dict]]:
        print(f"Starting error fixing (V2) for {self.language} project...")
        
        fix_results = []
        iteration_coverage_reports = []
        
        for iteration in range(self.max_fix_iterations):
            print(f"\n=== Fix Iteration {iteration + 1}/{self.max_fix_iterations} ===")
            print("Step 1: Running tests to collect errors...")
            error_output = self._run_coverage_with_errors()
            
            if not error_output.strip():
                print("No errors found in this iteration.")
                break
            print("Step 2: Analyzing errors...")
            errors = self._analyze_errors(error_output)
            
            if not errors:
                print("No parseable errors found.")
                break
            
            print(f"Found {len(errors)} errors to fix")
            print("Step 3: Fixing errors...")
            iteration_fixes = self._fix_all_errors(errors)
            fix_results.extend(iteration_fixes)

            successful_fixes = [fix for fix in iteration_fixes if fix.success]
            if not successful_fixes:
                print("No successful fixes in this iteration.")
                break
            
            print(f"Successfully fixed {len(successful_fixes)} errors in this iteration.")
            print(f"Step 4: Collecting coverage after iteration {iteration + 1}...")
            iteration_coverage = self.coverage_analyzer.collect_coverage()
            iteration_coverage_reports.append({
                'iteration': iteration + 1,
                'coverage_report': iteration_coverage,
                'errors_fixed': len(successful_fixes)
            })

        if not iteration_coverage_reports:
            print("\nStep 5: Collecting final coverage...")
            final_coverage = self.coverage_analyzer.collect_coverage()
        else:
            final_coverage = iteration_coverage_reports[-1]['coverage_report']
        
        return fix_results, final_coverage, iteration_coverage_reports
    
    def _run_coverage_with_errors(self) -> str:
        try:
            coverage_cmd = (
                "coverage run --source='.' "
                "--omit='**/tests/**,**/test_*.py,**/*_test.py,**/__init__.py,"
                "**/.venv/**,**/.tox/**,**/.pytest_cache/**' "
                "-m pytest --continue-on-collection-errors"
            )

            result = self.docker_runner.run_command(coverage_cmd)
            error_output = result.get("stderr", "")
            if not error_output:
                error_output = result.get("stdout", "")
            
            return error_output
            
        except Exception as e:
            print(f"Error running coverage command: {e}")
            return ""
    
    def _analyze_errors(self, error_output: str) -> List[ErrorInfo]:
        if not self.llm_client:
            print("No LLM client available for error analysis")
            return []
        
        try:
            user_prompt = ERROR_ANALYSIS_USER_PROMPT.format(ERROR_LOG=error_output)
            messages = [
                {"role": "system", "content": ERROR_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
            # Call LLM
            response = self.llm_client.query(messages)
            
            # Parse JSON response
            response_json = json.loads(response)
            errors = response_json.get("errors", [])
            
            # Convert to ErrorInfo objects
            error_infos = []
            for error in errors:
                error_info = ErrorInfo(
                    file_path=error.get("file_path", ""),
                    line_range=error.get("range", [1, 1]),
                    message=error.get("message", "")
                )
                error_infos.append(error_info)
            
            return error_infos
            
        except Exception as e:
            print(f"Error analyzing errors with LLM: {e}")
            return []
    
    def _fix_all_errors(self, errors: List[ErrorInfo]) -> List[FixResultV2]:
        """Fix all errors"""
        fix_results = []
        
        for i, error in enumerate(errors, 1):
            print(f"  Fixing error {i}/{len(errors)}: {error.file_path}:{error.line_range}")
            
            try:
                fix_result = self._fix_single_error(error)
                fix_results.append(fix_result)
                
                if fix_result.success:
                    if fix_result.fix_type == "code":
                        print(f"    ✓ Successfully fixed code error in {error.file_path}")
                    elif fix_result.fix_type == "command":
                        print(f"    ✓ Successfully executed commands for {error.file_path}")
                        print(f"      Commands: {', '.join(fix_result.commands)}")
                else:
                    print(f"    ✗ Failed to fix error: {fix_result.error_message}")
                    
            except Exception as e:
                print(f"    ✗ Exception while fixing error: {e}")
                fix_results.append(FixResultV2(
                    file_path=error.file_path,
                    original_code="",
                    fix_type="unfixable",
                    success=False,
                    error_message=str(e)
                ))
        
        return fix_results
    
    def _fix_single_error(self, error: ErrorInfo) -> FixResultV2:
        """Fix a single error"""
        try:
            # 1. Read file content
            file_content = self._read_file_from_container(error.file_path)
            if not file_content:
                return FixResultV2(
                    file_path=error.file_path,
                    original_code="",
                    fix_type="unfixable",
                    success=False,
                    error_message="Failed to read file content"
                )
            
            # 2. Add line numbers and extract error block
            lines = file_content.split('\n')
            numbered_full_code = self._add_line_numbers(file_content)
            
            # Extract error block (with some context)
            start_line = max(1, error.line_range[0] - 2)  # Add 2 lines of context above
            end_line = min(len(lines), error.line_range[1] + 2)  # Add 2 lines of context below
            
            error_block_lines = lines[start_line-1:end_line]
            numbered_error_block = self._add_line_numbers('\n'.join(error_block_lines), start_line)
            
            # 3. Use LLM to get fix suggestions
            fix_response = self._get_fix_from_llm(
                numbered_full_code, numbered_error_block, error.message
            )
            
            # 4. Execute corresponding operations based on fix type
            if fix_response["fix_type"] == "code":
                # Code fix
                fixed_code = fix_response.get("fixed_code", "").strip()
                if not fixed_code:
                    return FixResultV2(
                        file_path=error.file_path,
                        original_code='\n'.join(error_block_lines),
                        fix_type="unfixable",
                        success=False,
                        error_message="LLM returned empty fix"
                    )
                
                # Apply code fix
                success = self._apply_code_fix_to_file(error.file_path, error_block_lines, fixed_code, start_line-1, end_line)
                
                return FixResultV2(
                    file_path=error.file_path,
                    original_code='\n'.join(error_block_lines),
                    fix_type="code",
                    fixed_code=fixed_code,
                    language=fix_response.get("language", self.language),
                    success=success,
                    error_message=None if success else "Failed to apply code fix to file"
                )
            
            elif fix_response["fix_type"] == "command":
                # Command fix
                commands = fix_response.get("commands", [])
                description = fix_response.get("description", "")
                
                if not commands:
                    return FixResultV2(
                        file_path=error.file_path,
                        original_code='\n'.join(error_block_lines),
                        fix_type="unfixable",
                        success=False,
                        error_message="No commands provided"
                    )
                
                # Execute commands
                success = self._execute_commands(commands)
                
                return FixResultV2(
                    file_path=error.file_path,
                    original_code='\n'.join(error_block_lines),
                    fix_type="command",
                    commands=commands,
                    description=description,
                    success=success,
                    error_message=None if success else "Failed to execute commands"
                )
            
            else:
                # Cannot be fixed
                return FixResultV2(
                    file_path=error.file_path,
                    original_code='\n'.join(error_block_lines),
                    fix_type="unfixable",
                    reason=fix_response.get("reason", "Unknown reason"),
                    success=False,
                    error_message=fix_response.get("reason", "Error cannot be fixed")
                )
            
        except Exception as e:
            return FixResultV2(
                file_path=error.file_path,
                original_code="",
                fix_type="unfixable",
                success=False,
                error_message=str(e)
            )
    
    def _read_file_from_container(self, file_path: str) -> str:
        """Read file content from Docker container"""
        try:
            # Ensure file path is relative to /testbed
            if file_path.startswith('/'):
                container_path = file_path
            else:
                container_path = f"/testbed/{file_path}"
            
            cmd = f"cat {container_path}"
            result = self.docker_runner.run_command(cmd)
            
            if result.get("returncode") == 0:
                return result.get("stdout", "")
            else:
                print(f"Failed to read file {file_path}: {result.get('stderr')}")
                return ""
                
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return ""
    
    def _add_line_numbers(self, content: str, start_line: int = 1) -> str:
        """Add line numbers to code"""
        lines = content.split('\n')
        numbered_lines = []
        
        for i, line in enumerate(lines):
            line_num = start_line + i
            numbered_lines.append(f"{line_num:4d}: {line}")
        
        return '\n'.join(numbered_lines)
    
    def _get_fix_from_llm(self, full_code: str, error_block: str, error_message: str) -> Dict:
        """Get fix suggestions using LLM"""
        if not self.llm_client:
            return {"fix_type": "unfixable", "reason": "No LLM client available"}
        
        try:
            user_prompt = UNIT_TESTS_FIX_V2_USER_PROMPT.format(
                LANGUAGE=self.language,
                FULL_CODE=full_code,
                ERROR_BLOCK=error_block,
                ERROR_MESSAGE=error_message
            )
            
            # Build message list
            messages = [
                {"role": "system", "content": UNIT_TESTS_FIX_V2_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ]
            
            response = self.llm_client.query(messages)
            
            # Parse JSON response
            return json.loads(response)
            
        except Exception as e:
            print(f"Error getting fix from LLM: {e}")
            return {"fix_type": "unfixable", "reason": str(e)}
    
    def _apply_code_fix_to_file(self, file_path: str, original_lines: List[str], fixed_code: str, 
                               start_index: int, end_index: int) -> bool:
        """Apply code fix to file"""
        try:
            # Read current complete file content
            current_content = self._read_file_from_container(file_path)
            if not current_content:
                return False
            
            current_lines = current_content.split('\n')
            
            # Split fixed code into lines
            fixed_lines = fixed_code.split('\n')
            
            # Replace specified range of lines
            new_lines = current_lines[:start_index] + fixed_lines + current_lines[end_index:]
            new_content = '\n'.join(new_lines)
            
            # Write back to file
            return self._write_file_to_container(file_path, new_content)
            
        except Exception as e:
            print(f"Error applying code fix to file {file_path}: {e}")
            return False
    
    def _execute_commands(self, commands: List[str]) -> bool:
        """Execute command list"""
        try:
            for cmd in commands:
                print(f"    Executing: {cmd}")
                result = self.docker_runner.run_command(cmd)
                
                if result.get("returncode") != 0:
                    print(f"    Command failed: {cmd}")
                    print(f"    Error: {result.get('stderr', '')}")
                    return False
                
                print(f"    Command succeeded: {cmd}")
            
            return True
            
        except Exception as e:
            print(f"Error executing commands: {e}")
            return False
    
    def _write_file_to_container(self, file_path: str, content: str) -> bool:
        """Write content to file in Docker container"""
        try:
            # Ensure file path is relative to /testbed
            if file_path.startswith('/'):
                container_path = file_path
            else:
                container_path = f"/testbed/{file_path}"
            
            # Use base64 encoding to avoid escape issues
            import base64
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
            
            # Decode and write file in container
            cmd = f'echo "{encoded_content}" | base64 -d > {container_path}'
            result = self.docker_runner.run_command(cmd)
            
            return result.get("returncode") == 0
            
        except Exception as e:
            print(f"Error writing file {file_path}: {e}")
            return False


def create_error_fixer_v2(container_name: str = None,
                         docker_image: str = None,
                         language: str = "python",
                         temp_dir: str = "./docker_output/error_fix_exp_v2",
                         llm_client=None,
                         max_fix_iterations: int = 3) -> CoverageBasedErrorFixerV2:
    """Factory function to create V2 version error fixer"""
    return CoverageBasedErrorFixerV2(
        container_name=container_name,
        images=docker_image,
        language=language,
        temp_dir=temp_dir,
        llm_client=llm_client,
        max_fix_iterations=max_fix_iterations
    )


# if __name__ == "__main__":
    # import argparse
    
    # parser = argparse.ArgumentParser(description="Error fixer V2 with Docker support")
    # parser.add_argument("--container", required=True, help="Docker container name")
    # parser.add_argument("--image", help="Docker image name (if container doesn't exist)")
    # parser.add_argument("--language", default="python", choices=["python", "java"], 
    #                    help="Programming language")
    # parser.add_argument("--temp-dir", default="./docker_output/error_fix_exp_v2",
    #                    help="Temporary directory for output")
    # parser.add_argument("--model", default="claude-3.5-sonnet", help="LLM model to use")
    # parser.add_argument("--max-iterations", type=int, default=3, 
    #                    help="Maximum fix iterations")
    
    # args = parser.parse_args()
    
    # # Initialize LLM client
    # llm_client = CopilotProxyLLMClient(model=args.model)
    
    # # Create error fixer
    # fixer = create_error_fixer_v2(
    #     container_name=args.container,
    #     docker_image=args.image,
    #     language=args.language,
    #     temp_dir=args.temp_dir,
    #     llm_client=llm_client,
    #     max_fix_iterations=args.max_iterations
    # )
    
    # # Execute error fixing
    # fix_results, coverage_report, iteration_coverage_reports = fixer.fix_errors_and_collect_coverage()
    
    # # Output results
    # print(f"\n=== Fix Results Summary (V2) ===")
    # print(f"Total fixes attempted: {len(fix_results)}")
    # successful_fixes = [fix for fix in fix_results if fix.success]
    # print(f"Successful fixes: {len(successful_fixes)}")
    
    # # Category statistics
    # code_fixes = [fix for fix in successful_fixes if fix.fix_type == "code"]
    # command_fixes = [fix for fix in successful_fixes if fix.fix_type == "command"]
    # unfixable = [fix for fix in fix_results if fix.fix_type == "unfixable"]
    
    # print(f"Code fixes: {len(code_fixes)}")
    # print(f"Command fixes: {len(command_fixes)}")
    # print(f"Unfixable errors: {len(unfixable)}")
    
    # if coverage_report:
    #     print(f"\n=== Final Coverage ===")
    #     print(f"Coverage: {coverage_report.coverage_percentage:.2f}%")
    
    # for i, fix in enumerate(fix_results, 1):
    #     status = "✓" if fix.success else "✗"
    #     print(f"{i}. {status} [{fix.fix_type}] {fix.file_path}")
    #     if fix.fix_type == "command" and fix.commands:
    #         print(f"   Commands: {', '.join(fix.commands)}")
    #     if not fix.success and fix.error_message:
    #         print(f"   Error: {fix.error_message}")
