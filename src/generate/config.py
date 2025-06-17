# Coverage-Based Test Generator Configuration
# 基于覆盖率的测试生成器配置文件

# LLM配置
LLM_CONFIG = {
    # 默认使用CopilotProxyLLMClient
    "default_client": "copilot",
    
    # 可选的LLM客户端配置
    "clients": {
        "copilot": {
            "class": "CopilotProxyLLMClient",
            "config": {
                "integration_id": "autodev-test",
                "model": "gpt-4o"
            }
        },
        # 可以添加其他LLM客户端配置
        # "openai": {
        #     "class": "OpenAIClient",
        #     "config": {
        #         "api_key": "your-api-key",
        #         "model": "gpt-4"
        #     }
        # }
    },
    
    # LLM调用参数
    "generation_params": {
        "max_tokens": 4000,
        "temperature": 0.1,  # 较低的温度以获得更一致的代码生成
        "timeout": 30        # 超时时间（秒）
    }
}

# 覆盖率分析配置
COVERAGE_CONFIG = {
    "python": {
        # 默认测试命令
        "test_command": "python -m pytest",
        
        # 源代码目录
        "source_dirs": ["src", "lib", "."],
        
        # 覆盖率配置文件
        "coverage_config": ".coveragerc",
        
        # 忽略的文件和目录
        "ignore_patterns": [
            "*/tests/*",
            "*/test_*",
            "*/__pycache__/*",
            "*/venv/*",
            "*/env/*",
            "*/.git/*"
        ],
        
        # 最小覆盖率阈值
        "min_coverage_threshold": 80
    },
    
    "java": {
        # 默认测试命令
        "test_command": "mvn test",
        
        # 源代码目录
        "source_dirs": ["src/main/java"],
        "test_dirs": ["src/test/java"],
        
        # JaCoCo配置
        "jacoco_config": {
            "xml_report_path": "target/site/jacoco/jacoco.xml",
            "html_report_path": "target/site/jacoco/index.html"
        },
        
        # 忽略的包和类
        "ignore_patterns": [
            "*/test/*",
            "*/tests/*",
            "*Test.java",
            "*Tests.java",
            "*/target/*"
        ],
        
        # 最小覆盖率阈值
        "min_coverage_threshold": 75
    }
}

# 测试生成配置
TEST_GENERATION_CONFIG = {
    # 默认最大处理文件数
    "default_max_files": 5,
    
    # 每个文件最大未覆盖行数
    "max_uncovered_lines_per_file": 50,
    
    # 测试生成策略
    "generation_strategy": {
        # 优先级：按未覆盖行数排序
        "prioritize_by_uncovered_count": True,
        
        # 跳过测试文件
        "skip_test_files": True,
        
        # 跳过生成的文件
        "skip_generated_files": True,
        
        # 最小代码行数（跳过太小的文件）
        "min_file_lines": 10
    },
    
    # 代码质量过滤
    "code_quality_filters": {
        # 跳过只有注释的行
        "skip_comment_only_lines": True,
        
        # 跳过空行
        "skip_empty_lines": True,
        
        # 跳过只有pass语句的行
        "skip_pass_statements": True,
        
        # 跳过简单的getter/setter
        "skip_simple_accessors": True
    }
}

# 测试文件放置配置
TEST_PLACEMENT_CONFIG = {
    "python": {
        # 测试目录结构
        "test_directory": "tests",
        
        # 测试文件命名模式
        "test_file_pattern": "test_{filename}.py",
        
        # 是否镜像源代码目录结构
        "mirror_source_structure": True,
        
        # 额外的测试目录
        "additional_test_dirs": ["tests/unit", "tests/integration"],
        
        # conftest.py配置
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
        # 测试目录结构
        "test_directory": "src/test/java",
        
        # 测试文件命名模式
        "test_file_pattern": "{classname}Test.java",
        
        # 是否镜像包结构
        "mirror_package_structure": True,
        
        # 测试资源目录
        "test_resources_dir": "src/test/resources"
    }
}

# 报告生成配置
REPORT_CONFIG = {
    # 默认报告文件名
    "default_report_filename": "coverage_test_generation_report.md",
    
    # 报告格式
    "formats": ["markdown", "html", "json"],
    
    # 报告内容配置
    "include_sections": {
        "coverage_summary": True,
        "test_generation_summary": True,
        "generated_test_code": True,
        "uncovered_code_details": True,
        "recommendations": True
    },
    
    # HTML报告配置
    "html_config": {
        "template": "default",
        "include_css": True,
        "include_syntax_highlighting": True
    }
}

# 日志配置
LOGGING_CONFIG = {
    "level": "INFO",  # DEBUG, INFO, WARNING, ERROR
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "file": "coverage_test_generator.log"
}

# 缓存配置
CACHE_CONFIG = {
    # 是否启用缓存
    "enabled": True,
    
    # 缓存目录
    "cache_dir": ".coverage_test_cache",
    
    # 缓存过期时间（小时）
    "expiry_hours": 24,
    
    # 缓存的内容
    "cache_items": {
        "coverage_reports": True,
        "related_code_searches": True,
        "llm_responses": False  # 出于一致性考虑，不缓存LLM响应
    }
}

# 性能优化配置
PERFORMANCE_CONFIG = {
    # 并发处理
    "enable_parallel_processing": True,
    "max_workers": 4,
    
    # 批处理大小
    "batch_size": 5,
    
    # 超时设置
    "timeouts": {
        "coverage_analysis": 300,  # 5分钟
        "test_generation": 120,    # 2分钟
        "llm_call": 30            # 30秒
    }
}

# 验证配置
VALIDATION_CONFIG = {
    # 是否验证生成的测试
    "validate_generated_tests": True,
    
    # 验证方式
    "validation_methods": {
        "syntax_check": True,      # 语法检查
        "import_check": True,      # 导入检查
        "basic_execution": False   # 基本执行测试（可能较慢）
    },
    
    # 验证失败时的行为
    "on_validation_failure": "warn"  # "warn", "skip", "error"
}

# 实验性功能配置
EXPERIMENTAL_CONFIG = {
    # 是否启用实验性功能
    "enabled": False,
    
    # 功能开关
    "features": {
        "ai_test_improvement": False,     # AI辅助测试改进
        "mutation_testing": False,       # 变异测试
        "performance_testing": False,    # 性能测试生成
        "integration_testing": False     # 集成测试生成
    }
}
