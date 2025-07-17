# Coverage-Based Test Generator Configuration
# Configuration file for coverage-based test generator

# LLM Configuration
LLM_CONFIG = {
    # Use CopilotProxyLLMClient by default
    "default_client": "copilot",
    
    # Optional LLM client configurations
    "clients": {
        "copilot": {
            "class": "CopilotProxyLLMClient",
            "config": {
                "integration_id": "autodev-test",
                "model": "gpt-4o"
            }
        },
        # Can add other LLM client configurations
        # "openai": {
        #     "class": "OpenAIClient",
        #     "config": {
        #         "api_key": "your-api-key",
        #         "model": "gpt-4"
        #     }
        # }
    },
    
    # LLM call parameters
    "generation_params": {
        "max_tokens": 4000,
        "temperature": 0.1,  # Lower temperature for more consistent code generation
        "timeout": 30        # Timeout in seconds
    }
}

# Coverage analysis configuration
COVERAGE_CONFIG = {
    "python": {
        # Default test command
        "test_command": "python -m pytest",
        
        # Source code directories
        "source_dirs": ["src", "lib", "."],
        
        # Coverage configuration file
        "coverage_config": ".coveragerc",
        
        # Ignored files and directories
        "ignore_patterns": [
            "*/tests/*",
            "*/test_*",
            "*/__pycache__/*",
            "*/venv/*",
            "*/env/*",
            "*/.git/*"
        ],
        
        # Minimum coverage threshold
        "min_coverage_threshold": 80
    },
    
    "java": {
        # Default test command
        "test_command": "mvn test",
        
        # Source code directories
        "source_dirs": ["src/main/java"],
        "test_dirs": ["src/test/java"],
        
        # JaCoCo configuration
        "jacoco_config": {
            "xml_report_path": "target/site/jacoco/jacoco.xml",
            "html_report_path": "target/site/jacoco/index.html"
        },
        
        # Ignored packages and classes
        "ignore_patterns": [
            "*/test/*",
            "*/tests/*",
            "*Test.java",
            "*Tests.java",
            "*/target/*"
        ],
        
        # Minimum coverage threshold
        "min_coverage_threshold": 75
    }
}

# Test generation configuration
TEST_GENERATION_CONFIG = {
    # Default maximum number of files to process
    "default_max_files": 5,
    
    # Maximum uncovered lines per file
    "max_uncovered_lines_per_file": 50,
    
    # Test generation strategy
    "generation_strategy": {
        # Priority: sort by uncovered line count
        "prioritize_by_uncovered_count": True,
        
        # Skip test files
        "skip_test_files": True,
        
        # Skip generated files
        "skip_generated_files": True,
        
        # Minimum code lines (skip files that are too small)
        "min_file_lines": 10
    },
    
    # Code quality filters
    "code_quality_filters": {
        # Skip comment-only lines
        "skip_comment_only_lines": True,
        
        # Skip empty lines
        "skip_empty_lines": True,
        
        # Skip lines with only pass statements
        "skip_pass_statements": True,
        
        # Skip simple getter/setter methods
        "skip_simple_accessors": True
    }
}

# Test file placement configuration
TEST_PLACEMENT_CONFIG = {
    "python": {
        # Test directory structure
        "test_directory": "tests",
        
        # Test file naming pattern
        "test_file_pattern": "test_{filename}.py",
        
        # Whether to mirror source code directory structure
        "mirror_source_structure": True,
        
        # Additional test directories
        "additional_test_dirs": ["tests/unit", "tests/integration"],
        
        # conftest.py configuration
        "create_conftest": True,
        "conftest_content": '''
import pytest
import sys
from pathlib import Path

# Add src to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))
'''
    },
    
    "java": {
        # Test directory structure
        "test_directory": "src/test/java",
        
        # Test file naming pattern
        "test_file_pattern": "{classname}Test.java",
        
        # Whether to mirror package structure
        "mirror_package_structure": True,
        
        # Test resources directory
        "test_resources_dir": "src/test/resources"
    }
}

# Report generation configuration
REPORT_CONFIG = {
    # Default report filename
    "default_report_filename": "coverage_test_generation_report.md",
    
    # Report formats
    "formats": ["markdown", "html", "json"],
    
    # Report content configuration
    "include_sections": {
        "coverage_summary": True,
        "test_generation_summary": True,
        "generated_test_code": True,
        "uncovered_code_details": True,
        "recommendations": True
    },
    
    # HTML report configuration
    "html_config": {
        "template": "default",
        "include_css": True,
        "include_syntax_highlighting": True
    }
}

# Logging configuration
LOGGING_CONFIG = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "coverage_test_generator.log"
}

# Cache configuration
CACHE_CONFIG = {
    # Whether to enable caching
    "enabled": True,
    
    # Cache directory
    "cache_dir": ".coverage_test_cache",
    
    # Cache expiry time (hours)
    "expiry_hours": 24,
    
    # Cached content
    "cache_items": {
        "coverage_reports": True,
        "related_code_searches": True,
        "llm_responses": False  # Don't cache LLM responses for consistency
    }
}

# Performance optimization configuration
PERFORMANCE_CONFIG = {
    # Concurrent processing
    "enable_parallel_processing": True,
    "max_workers": 4,
    
    # Batch processing size
    "batch_size": 5,
    
    # Timeout settings
    "timeouts": {
        "coverage_analysis": 300,  # 5 minutes
        "test_generation": 120,    # 2 minutes
        "llm_call": 30            # 30 seconds
    }
}

# Validation configuration
VALIDATION_CONFIG = {
    # Whether to validate generated tests
    "validate_generated_tests": True,
    
    # Validation methods
    "validation_methods": {
        "syntax_check": True,      # Syntax checking
        "import_check": True,      # Import checking
        "basic_execution": False   # Basic execution test (may be slow)
    },
    
    # Behavior on validation failure
    "on_validation_failure": "warn"  # "warn", "skip", "error"
}

# Experimental features configuration
EXPERIMENTAL_CONFIG = {
    # Whether to enable experimental features
    "enabled": False,
    
    # Feature switches
    "features": {
        "ai_test_improvement": False,     # AI-assisted test improvement
        "mutation_testing": False,       # Mutation testing
        "performance_testing": False,    # Performance test generation
        "integration_testing": False     # Integration test generation
    }
}
