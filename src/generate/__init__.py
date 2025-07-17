# -*- coding: utf-8 -*-
from .coverage_analyzer import (
    CoverageAnalyzer,
    PythonCoverageAnalyzer,
    CoverageReport,
    UncoveredCode,
    CoverageType,
)

from .unit_test_generator import (
    CoverageBasedTestGenerator,
    GeneratedTest,
)

from .config import (
    LLM_CONFIG,
    COVERAGE_CONFIG,
    TEST_GENERATION_CONFIG,
    TEST_PLACEMENT_CONFIG,
    REPORT_CONFIG,
    LOGGING_CONFIG,
    CACHE_CONFIG,
    PERFORMANCE_CONFIG,
    VALIDATION_CONFIG,
    EXPERIMENTAL_CONFIG
)

__version__ = "1.0.0"
__author__ = "Coverage Test Generator Team"

__all__ = [
    # Coverage analysis
    "CoverageAnalyzer",
    "PythonCoverageAnalyzer", 
    "JavaCoverageAnalyzer",
    "CoverageReport",
    "UncoveredCode",
    "CoverageType",
    "create_coverage_analyzer",
    "analyze_project_coverage",
    
    # Test generation
    "CoverageBasedTestGenerator",
    "GeneratedTest",
    "TestPlacement",
    
    # Configuration
    "LLM_CONFIG",
    "COVERAGE_CONFIG",
    "TEST_GENERATION_CONFIG",
    "TEST_PLACEMENT_CONFIG",
    "REPORT_CONFIG",
    "LOGGING_CONFIG",
    "CACHE_CONFIG",
    "PERFORMANCE_CONFIG",
    "VALIDATION_CONFIG",
    "EXPERIMENTAL_CONFIG",
]

