#!/usr/bin/env python3
"""
Java JaCoCo Coverage Parser for generating uncovered_code.json
This script is designed to run inside Docker containers with Java projects.
"""

import os
import sys
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def find_jacoco_reports(repo_path):
    """Find all JaCoCo XML report files"""
    report_paths = []
    print(f"Searching for JaCoCo reports in: {repo_path}")
    
    for dirpath, dirnames, filenames in os.walk(repo_path):
        for filename in filenames:
            if filename == 'jacoco.xml':
                report_paths.append(os.path.join(dirpath, filename))
    
    print(f"Found {len(report_paths)} JaCoCo report(s): {report_paths}")
    return report_paths


def parse_jacoco_report(report_path, repo_path):
    """Parse a JaCoCo XML report and extract uncovered lines"""
    if not os.path.exists(report_path):
        print(f"JaCoCo report not found at {report_path}")
        return {}
    
    try:
        tree = ET.parse(report_path)
        root = tree.getroot()
        
        file_coverage_map = {}
        
        for package in root.findall('./package'):
            package_name = package.get('name', '')
            
            for sourcefile in package.findall('./sourcefile'):
                sourcefile_name = sourcefile.get('name', '')
                
                if not sourcefile_name.endswith('.java'):
                    continue
                
                # Construct the relative file path
                if package_name:
                    # Convert package path to directory structure
                    package_path = package_name.replace('/', os.sep)
                    relative_path = os.path.join('src', 'main', 'java', package_path, sourcefile_name)
                else:
                    relative_path = os.path.join('src', 'main', 'java', sourcefile_name)
                
                # Find the actual file in the repository using multiple search strategies
                actual_file_path = None
                search_paths = []
                
                # Strategy 1: Standard Maven structure
                search_paths.append(os.path.join(repo_path, relative_path))
                
                # Strategy 2: Search in all subdirectories (for multi-module projects)
                if package_name:
                    package_path = package_name.replace('/', os.sep)
                    # Search in all subdirectories for the file
                    for root, dirs, files in os.walk(repo_path):
                        if sourcefile_name in files:
                            candidate_path = os.path.join(root, sourcefile_name)
                            # Check if the package structure matches
                            if package_path in candidate_path.replace(os.sep, '/'):
                                search_paths.append(candidate_path)
                
                # Strategy 3: Direct search by filename
                for root, dirs, files in os.walk(repo_path):
                    if sourcefile_name in files:
                        candidate_path = os.path.join(root, sourcefile_name)
                        if candidate_path not in search_paths:
                            search_paths.append(candidate_path)
                
                # Find the first existing file
                for search_path in search_paths:
                    if os.path.exists(search_path):
                        actual_file_path = search_path
                        break
                
                if not actual_file_path:
                    print(f"⚠ Source file not found: {relative_path}")
                    continue
                
                # Extract uncovered lines
                uncovered_lines = []
                covered_lines = []
                
                for line in sourcefile.findall('./line'):
                    line_nr = int(line.get('nr', '0'))
                    covered_instructions = int(line.get('ci', '0'))
                    missed_instructions = int(line.get('mi', '0'))
                    
                    if covered_instructions == 0 and missed_instructions > 0:
                        # Line has missed instructions (definitely uncovered)
                        uncovered_lines.append(line_nr)
                    elif covered_instructions > 0:
                        # Line has covered instructions
                        covered_lines.append(line_nr)
                
                # If no coverage data found at all, this might indicate no tests were run
                # In this case, we should consider the entire file as potentially uncovered
                if not uncovered_lines and not covered_lines and actual_file_path:
                    print(f"ℹ No coverage data found for {relative_path}, treating as potentially uncovered")
                    # Read the file and mark all non-empty, non-comment lines as uncovered
                    try:
                        with open(actual_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            lines = f.readlines()
                            for i, line in enumerate(lines, 1):
                                stripped = line.strip()
                                # Skip empty lines, comments, and simple declarations
                                if (stripped and 
                                    not stripped.startswith('//') and 
                                    not stripped.startswith('/*') and 
                                    not stripped.startswith('*') and
                                    not stripped.startswith('package ') and
                                    not stripped.startswith('import ') and
                                    stripped not in ['{', '}', '}']):
                                    uncovered_lines.append(i)
                    except Exception as e:
                        print(f"Error reading file for uncovered analysis: {e}")
                
                if uncovered_lines:
                    # Use relative path for consistency
                    rel_path = os.path.relpath(actual_file_path, repo_path)
                    file_coverage_map[rel_path] = {
                        'uncovered_lines': sorted(uncovered_lines),
                        'actual_path': actual_file_path
                    }
        
        return file_coverage_map
        
    except Exception as e:
        print(f"Error parsing JaCoCo report {report_path}: {e}")
        return {}


def read_file_content(file_path):
    """Read the full content of a Java file"""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()
    except Exception as e:
        print(f"Error reading file {file_path}: {e}")
        return f"// Error reading file: {str(e)}"


def generate_uncovered_code_json(repo_path, output_path):
    """Generate uncovered_code.json file for Java projects"""
    try:
        # Find all JaCoCo reports
        jacoco_reports = find_jacoco_reports(repo_path)
        
        if not jacoco_reports:
            print("No JaCoCo reports found")
            return False
        
        # Aggregate coverage data from all reports
        all_file_coverage = {}
        
        for report_path in jacoco_reports:
            file_coverage = parse_jacoco_report(report_path, repo_path)
            
            # Merge coverage data (combine uncovered lines from multiple reports)
            for file_path, coverage_info in file_coverage.items():
                if file_path in all_file_coverage:
                    # Combine uncovered lines and remove duplicates
                    existing_lines = set(all_file_coverage[file_path]['uncovered_lines'])
                    new_lines = set(coverage_info['uncovered_lines'])
                    combined_lines = sorted(list(existing_lines.union(new_lines)))
                    all_file_coverage[file_path]['uncovered_lines'] = combined_lines
                else:
                    all_file_coverage[file_path] = coverage_info
        
        # Generate the final JSON structure
        uncovered_data = []
        
        for file_path, coverage_info in all_file_coverage.items():
            uncovered_lines = coverage_info['uncovered_lines']
            actual_path = coverage_info['actual_path']
            
            if uncovered_lines:  # Only include files with uncovered lines
                file_content = read_file_content(actual_path)
                
                uncovered_data.append({
                    "file_path": file_path,
                    "code": file_content,
                    "uncovered_lines": uncovered_lines
                })
        
        # Write the JSON file
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(uncovered_data, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Generated uncovered_code.json with {len(uncovered_data)} files")
        print(f"Total uncovered lines across all files: {sum(len(item['uncovered_lines']) for item in uncovered_data)}")
        
        return True
        
    except Exception as e:
        print(f"Error generating uncovered_code.json: {e}")
        return False


def main():
    """Main function"""
    if len(sys.argv) < 2:
        print("Usage: python3 java_coverage_parser.py <repo_path> [output_path]")
        sys.exit(1)
    
    repo_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.join(repo_path, 'uncovered_code.json')
    
    print(f"Java Coverage Parser")
    print(f"Repository path: {repo_path}")
    print(f"Output path: {output_path}")
    
    if not os.path.exists(repo_path):
        print(f"Repository path does not exist: {repo_path}")
        sys.exit(1)
    
    success = generate_uncovered_code_json(repo_path, output_path)
    
    if success:
        print("✓ Java coverage parsing completed successfully")
    else:
        print("✗ Java coverage parsing failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
